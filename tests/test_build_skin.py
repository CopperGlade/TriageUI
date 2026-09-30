import functools
import importlib.util
import io
import math
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from PIL import Image

import build_skin as skin

# A real EverQuest folder, used only by the checks against the stock skin, which are skipped without one.
EQ_DIRS = [os.environ.get('EQ_DIR', ''), r'C:\QUARM', '/Volumes/[C] Windows 11/QUARM']
# Stands in for the base skin's EQUI_Animations.xml.
BASE_ANIMATIONS = (
    '<?xml version="1.0" encoding="us-ascii"?>\r\n'
    '<XML ID="EQInterfaceDefinitionLanguage">\r\n'
    '  <Schema xmlns="EverQuestData" xmlns:dt="EverQuestDataTypes" />\r\n'
    '  <Ui2DAnimation item="A_Base"><Cycle>true</Cycle></Ui2DAnimation>\r\n'
    '  <Ui2DAnimation item="BlueIconBackground">\r\n'
    '    <Cycle>true</Cycle>\r\n'
    '  </Ui2DAnimation>\r\n'
    '</XML>\r\n'
)
# The order the client loads them in (default's EQUI.xml).
LOAD_ORDER = [skin.ANIMATIONS_FILE, skin.GROUP_FILE, skin.TARGET_FILE, skin.CASTING_FILE, skin.CASTSPELL_FILE,
              skin.CHAT_FILE, skin.PET_WINDOW_FILE, skin.CONTAINER_FILE, skin.ACTIONS_FILE, skin.SELECTOR_FILE,
              skin.HOTBUTTON_FILE,
              skin.BUFF_FILE, skin.SONG_FILE, skin.PLAYER_FILE, skin.BREATH_FILE, skin.RAID_FILE, skin.MERCHANT_FILE,
              skin.CONFIRM_FILE, skin.ITEM_FILE, skin.QUANTITY_FILE, skin.GIVE_FILE, skin.TRADE_FILE, skin.LOOT_FILE,
              skin.COMPASS_FILE, skin.BANK_FILE, skin.SKILLS_FILE, skin.SPELLBOOK_FILE, skin.INVENTORY_FILE,
              skin.TRACKING_FILE, skin.AA_FILE, skin.FRIENDS_FILE, skin.INSPECT_FILE]


@functools.cache
def files():
    return skin.skin_files(BASE_ANIMATIONS)


def decode(data):
    return Image.open(io.BytesIO(data)).convert('RGBA')


def pixels(image):
    # getdata is deprecated from Pillow 12; older Pillow has only getdata.
    return list(getattr(image, 'get_flattened_data', image.getdata)())


def parse(name):
    return ET.fromstring(files()[name])


def everything():
    """Every loaded XML file's definitions under one root, as the client merges them."""
    root = ET.Element('XML')
    for name in LOAD_ORDER:
        root.extend(list(parse(name)))
    return root


def items(root, tag):
    return {element.get('item'): element for element in root.iter(tag)}


def rect_of(anim):
    frame = anim.find('Frames')
    return (int(frame.find('Location/X').text), int(frame.find('Location/Y').text),
            int(frame.find('Size/CX').text), int(frame.find('Size/CY').text))


def box(element):
    return (int(element.find('Location/X').text), int(element.find('Location/Y').text),
            int(element.find('Size/CX').text), int(element.find('Size/CY').text))


def number(element, tag, default=0):
    found = element.find(tag)
    return int(found.text) if found is not None else default


def rgb(element, tag):
    found = element.find(tag)
    return tuple(int(found.find(c).text) for c in 'RGB')


def cut(atlas, anim):
    x, y, w, h = rect_of(anim)
    return atlas.crop((x, y, x + w, y + h))


def colors(anim):
    """The colors an animation draws: its rectangle of its texture."""
    texture = decode(files()[anim.find('Frames/Texture').text])
    x, y, w, h = rect_of(anim)
    return set(pixels(texture.crop((x, y, x + w, y + h))))


def direct_pieces(root, window):
    """The window's own pieces, not what its clips hold."""
    defined = {e.get('item'): e for e in root}
    return [defined[p.text] for p in window.findall('Pieces')]


def assemble(width, height):
    """A window frame as the client draws it: the frame template's border pieces cut from the TGA, corners
    in the corners, sides repeated along the edges, and the background texture repeated inside."""
    root = parse(skin.ANIMATIONS_FILE)
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(root, 'Ui2DAnimation')
    border = items(root, 'WindowDrawTemplate')[skin.FRAME_TEMPLATE].find('Border')

    def piece(side):
        return cut(atlas, anims[border.find(side).text])

    b = skin.BORDER
    window = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    background = decode(files()[skin.BACKGROUND_TEXTURE])
    for y in range(b, height - b, background.height):
        for x in range(b, width - b, background.width):
            window.paste(background.crop((0, 0, min(background.width, width - b - x),
                                          min(background.height, height - b - y))), (x, y))
    for side, x0, y0, horizontal in (('Top', b, 0, True), ('Bottom', b, height - b, True),
                                     ('Left', 0, b, False), ('Right', width - b, b, False)):
        image = piece(side)
        end = width - b if horizontal else height - b
        position = x0 if horizontal else y0
        while position < end:
            if horizontal:
                window.paste(image.crop((0, 0, min(image.width, end - position), image.height)), (position, y0))
                position += image.width
            else:
                window.paste(image.crop((0, 0, image.width, min(image.height, end - position))), (x0, position))
                position += image.height
    for side, x, y in (('TopLeft', 0, 0), ('TopRight', width - b, 0), ('BottomLeft', 0, height - b),
                       ('BottomRight', width - b, height - b)):
        window.paste(piece(side), (x, y))
    return window


def as_image(texture):
    image = Image.new('RGBA', (texture.width, texture.height))
    image.putdata([pixel for row in texture.rows for pixel in row])
    return image


def screen(name):
    """A window file and its window, which comes last, after any clips."""
    root = parse(name)
    assert root[-1].tag == 'Screen'
    return root, root[-1]


def button_controls(root):
    """Every Button control under root: not a Combobox's Button, which only names its arrow's template."""
    return [e for e in root.iter('Button') if len(e)]


def parts(root):
    return {e.get('item'): e for tag in ('Gauge', 'Label', 'Button') for e in root.iter(tag)}


def anchored_rect(element, inside):
    """Where the client draws an AutoStretch control in a window whose inside is that size (eqgame.exe's
    GetLocation, 0x5750C0): each edge its offset in from the near side, or in from the far side where its flag is
    false (every flag is true by default, in SIDL.xml)."""
    width, height = inside

    def edge(side, flag, far):
        offset = number(element, f'{side}AnchorOffset')
        return offset if element.findtext(flag, 'true') == 'true' else far - offset

    left, top = edge('Left', 'LeftAnchorToLeft', width), edge('Top', 'TopAnchorToTop', height)
    right, bottom = edge('Right', 'RightAnchorToLeft', width), edge('Bottom', 'BottomAnchorToTop', height)
    return left, top, right - left, bottom - top


def drawn_size(element):
    """A control's size as the client draws it: its Size, or an anchored one's where that doesn't depend on the
    window's size (both sides measured from the same edge)."""
    if element.findtext('AutoStretch') != 'true':
        return box(element)[2:]
    flags = [element.findtext(tag, 'true') for tag in
             ('LeftAnchorToLeft', 'RightAnchorToLeft', 'TopAnchorToTop', 'BottomAnchorToTop')]
    assert flags[0] == flags[1] and flags[2] == flags[3], element.get('item')
    return anchored_rect(element, (0, 0))[2:]


# Textures

def test_tga_is_uncompressed_32_bit_with_alpha_and_bottom_left_origin():
    texture = skin.Texture(3, 2)
    texture.rows = [[(255, 0, 0, 255), (0, 255, 0, 128), (0, 0, 255, 0)],
                    [(10, 20, 30, 40), (50, 60, 70, 80), (90, 100, 110, 120)]]
    data = skin.tga_bytes(texture)
    image_type, width, height, depth, descriptor = data[2], data[12] | data[13] << 8, data[14] | data[15] << 8, data[16], data[17]
    assert (image_type, width, height, depth) == (2, 3, 2, 32)
    assert descriptor & 0x0F == 8 and not descriptor & 0x20
    assert pixels(decode(data)) == [pixel for row in texture.rows for pixel in row]


def test_panel_is_the_overlay_colors_opaque_on_the_16_bit_steps():
    # Opaque: players set each window's alpha in game, and a baked-in 85% only stacked with theirs.
    # EQ Triage's (14, 18, 26) with green on a 16-bit step, the one channel whose dither could show:
    # snapping every channel made it (17, 17, 34), which the user saw as too blue.
    panel = skin.panel_texture(9, 9)
    assert panel.pixel(4, 4) == skin.PANEL_RGBA == (14, 17, 26, 255) == skin.snapped((*skin.PANEL_RGB, 255))
    # The top edge away from the corners: the 1px edge over the half-covered body, as Qt draws it.
    assert panel.pixel(4, 0) == skin.over(skin.EDGE_FADED, 1, skin.over(skin.PANEL_RGBA, 0.5))
    assert skin.EDGE_FADED == (255, 255, 255, 51)
    # Rounded corners: the corner pixel is nearly clear.
    assert panel.pixel(0, 0)[3] < 20


@pytest.mark.parametrize('name', ['triageui_pieces.tga', 'triageui_bg.tga', 'triageui_percent.tga',
                                  'triageui_field.tga', 'triageui_gutter.tga', 'triageui_book.tga',
                                  *skin.SPELL_ICON_SHEETS, *skin.GEM_ICON_SHEETS])
def test_every_texture_pixel_is_on_the_16_bit_steps(name):
    # The client dithers colors between the steps into a pattern (the buttons' hover and edges did).
    assert name in files()
    off = [p for p in pixels(decode(files()[name])) if not on_steps(p)]
    assert not off, off[:3]


def on_steps(rgba):
    """Whether a color's green and alpha, where a 16-bit dither shows, are on the steps."""
    return all(rgba[i] % skin.STEP == 0 for i in skin.SNAPPED_CHANNELS) and skin.SNAPPED_CHANNELS == (1, 3)


def test_panel_shortcut_matches_full_supersampling():
    fast = skin.panel_texture(23, 17)
    slow = skin.Texture(23, 17)
    step, samples = 1 / skin.SUPERSAMPLE, skin.SUPERSAMPLE ** 2
    for y in range(17):
        for x in range(23):
            inside = on_edge = 0
            for j in range(skin.SUPERSAMPLE):
                for i in range(skin.SUPERSAMPLE):
                    d = skin.rounded_rect_distance(x + (i + 0.5) * step, y + (j + 0.5) * step, 0.5, 0.5, 22.5, 16.5,
                                                   skin.CORNER_RADIUS)
                    inside += d < 0
                    on_edge += abs(d) <= 0.5
            slow.rows[y][x] = skin.over(skin.EDGE_FADED, on_edge / samples, skin.over(skin.PANEL_RGBA, inside / samples))
    assert fast.rows == slow.rows


def test_background_is_the_panel_body():
    background = decode(files()[skin.BACKGROUND_TEXTURE])
    assert set(pixels(background)) == {skin.PANEL_RGBA}


@pytest.mark.parametrize('size', [(9, 9), (37, 23), (200, 30)])
def test_frame_assembles_into_the_overlay_panel_at_any_size(size):
    assert pixels(assemble(*size)) == pixels(as_image(skin.snapped_art(skin.panel_texture(*size))))


def test_atlas_pieces_fit_without_overlap_and_repeat_their_edges_outward():
    atlas = decode(files()[skin.PIECES_TEXTURE])
    assert atlas.size == (skin.ATLAS_WIDTH, skin.ATLAS_HEIGHT)
    cells = []
    for anim in items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation').values():
        texture = anim.find('Frames/Texture')
        if texture is None or texture.text != skin.PIECES_TEXTURE:
            continue
        x, y, w, h = rect_of(anim)
        assert 1 <= x and x + w + 1 <= atlas.width and 1 <= y and y + h + 1 <= atlas.height
        if w == 0:
            continue  # draws nothing, so it has no cell of its own (the slider's left end cap)
        cells.append((x - 1, y - 1, x + w + 1, y + h + 1))
        for mx in range(x - 1, x + w + 1):
            for my in range(y - 1, y + h + 1):
                inside = (min(max(mx, x), x + w - 1), min(max(my, y), y + h - 1))
                assert atlas.getpixel((mx, my)) == atlas.getpixel(inside)
    cells = sorted(set(cells))  # the redefined stock backgrounds share our pieces' cells
    for i, a in enumerate(cells):
        for b in cells[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def test_every_bar_is_exactly_as_big_as_the_rest_of_its_gauge():
    # The client draws a gauge's track and fill at their own size: an 8px fill showed as an 8px bar in game.
    # So a bar's art is its whole length, and it fills the rest of its gauge, except in the group window,
    # where the rows stay full width for clicking and the bars are as long as the pet window's.
    root = everything()
    anims = items(root, 'Ui2DAnimation')
    # Not the hidden ones, which have no size.
    gauges = [g for g in root.iter('Gauge') if g.get('item').startswith('TUI_') and box(g)[2:] != (0, 0)]
    # The target's bar and %, the casting bar, your pet's bar and %, each group member, pet and %, the Player
    # window's HP and mana with their %s, its server tick and its XP and AA rates' %s, the spell bar's recast
    # bars and global recovery, the air bar, the spell book's memorizing and scribing bars, and the inventory's XP and
    # AA bars with their %s.
    assert len(gauges) == 6 + 3 * skin.GROUP_SIZE + 6 + skin.GEM_COUNT + 1 + 1 + 2 + 4
    for g in gauges:
        if g.find('GaugeDrawTemplate/Fill') is None or g.find('GaugeDrawTemplate/Fill').text == 'TUI_PercentSign':
            continue  # shown whole or not at all, not a bar: see the % and empty slot tests
        x, y, width, height = box(g)
        bar = (width - number(g, 'GaugeOffsetX'), height - number(g, 'GaugeOffsetY', 16))
        if g.get('item').startswith('TUI_GW_Gauge'):
            bar = (skin.GROUP_BAR_WIDTH, bar[1])
        if g.get('item').startswith('TUI_GW_PetGauge'):
            bar = (skin.GROUP_BAR_WIDTH - skin.PET_INDENT, bar[1])
        template = g.find('GaugeDrawTemplate')
        # Solid, each exactly its tint: see the group, player and inventory window tests and the server tick test.
        solid = (g.get('item').startswith(('TUI_GW_Gauge', 'TUI_GW_PetGauge'))
                 or g.get('item') in ('TUI_PW_PlayerMana', 'TUI_PW_ZealTick', 'TUI_IW_XPBar', 'TUI_IW_AABar'))
        fill = skin.WHITE if solid else skin.BAR_FILL
        for part, color in (('Background', skin.EDGE_FADED), ('Fill', fill)):
            if template.find(part) is None:
                continue
            anim = anims[template.find(part).text]
            assert rect_of(anim)[2:] == bar, g.get('item')
            assert colors(anim) == {color}


def test_button_art_is_the_button_size_in_every_state():
    root = everything()
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(root, 'Ui2DAnimation')
    # Not the hidden ones, nor the effect slots, which the client paints (see the effects tests). An anchored button
    # is drawn at its anchors' size (the bag window's: see its tests).
    buttons = [b for b in button_controls(root)
               if drawn_size(b) != (0, 0) and b.find('ButtonDrawTemplate/NormalDecal') is None]
    assert buttons
    for b in buttons:
        template = b.find('ButtonDrawTemplate')
        assert [e.tag for e in template] == list(skin.BUTTON_STATES)
        for state in template:
            assert cut(atlas, anims[state.text]).size == drawn_size(b)
    # Each labeled button size in use has its own art (the selector's icon toggles have theirs, and the hot button
    # window's macros and the coin boxes their own solid art: see their tests).
    buttons = [b for b in buttons if b.find('Text') is not None
               and not b.findtext('ButtonDrawTemplate/Normal').startswith(('TUI_HotButton', 'TUI_Coin',
                                                                            'TUI_BankCoin'))]
    assert {drawn_size(b) for b in buttons} == set(skin.BUTTON_LABELS)
    art = {state: cut(atlas, anims[f'TUI_{skin.button_art(skin.BUTTON_WIDTH, skin.BUTTON_HEIGHT, "Invite", state)}'])
           for state in skin.BUTTON_LOOKS}
    beside = (4, skin.BUTTON_HEIGHT // 2)  # inside the edge, left of the label
    # A faint white wash over the panel; hovered and pressed are opaque slate, the see-through hover
    # having shown a pattern in game, pressed darker than hovered.
    assert art['Normal'].getpixel(beside) == (255, 255, 255, 17)
    assert art['Flyby'].getpixel(beside) == (51, 68, 85, 255)
    assert art['Pressed'].getpixel(beside)[3] == 255
    assert sum(art['Pressed'].getpixel(beside)[:3]) < sum(art['Flyby'].getpixel(beside)[:3])


def test_button_labels_are_our_own_lettering_centered_in_the_art():
    # The client's font 2 looked squished and 3 too big, and no font can be letter-spaced: the labels are
    # drawn into the art, LETTER_SPACING apart, and the buttons' own text is empty.
    root = everything()
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(root, 'Ui2DAnimation')
    # (The Actions window's buttons carry their names in font 3 instead: see its tests.)
    labeled = [b for b in button_controls(root)
               if b.find('Text') is not None and box(b)[2:] != (0, 0) and b.find('Font') is None]
    assert {b.findtext('Text') for b in labeled} == {''}
    assert skin.LETTER_SPACING == 2
    for (width, height), labels in skin.BUTTON_LABELS.items():
        for label in labels:
            text_width, ink = skin.lettering(label)
            left = (width - text_width) // 2
            # Centered, with room to spare inside the edge.
            assert left >= 4 and width - (left + text_width) >= 4 and abs((width - text_width) - 2 * left) <= 1
            for state in skin.BUTTON_LOOKS:
                image = cut(atlas, anims[f'TUI_{skin.button_art(width, height, label, state)}'])
                inked = {(x, y) for x in range(width) for y in range(height)
                         if image.getpixel((x, y))[:3] == skin.snapped((*skin.TEXT_RGB, 255))[:3]}
                assert {(left + x, skin.LABEL_TOP + y) for x, y in ink} <= inked, (label, state)
    # Every glyph is 7 rows of one width, sitting on the 7th, but the space, which has no ink, and p, g and y, whose
    # tails go a row below (on the line, p read as a small capital P; a straight stem would make g read as q).
    for letter, rows in skin.LABEL_GLYPHS.items():
        assert len(rows) == skin.LABEL_HEIGHT + (letter in 'pgy') and len({len(r) for r in rows}) == 1, letter
        assert ('#' in rows[skin.LABEL_HEIGHT - 1]) != (letter == ' '), letter
        if letter in 'gy':
            assert rows[-1].count('#') > 1, letter  # a hook, not a straight stem
    assert skin.LABEL_TOP + skin.LABEL_HEIGHT + 1 < skin.BUTTON_HEIGHT - 1  # the tails clear the button's edge
    # Words are a padding apart: the space and the spacing either side of it.
    assert len(skin.LABEL_GLYPHS[' '][0]) + 2 * skin.LETTER_SPACING == skin.PADDING


def test_every_button_color_is_one_a_16_bit_texture_holds_exactly():
    # The client may keep our art as a 16-bit texture (16 steps per channel) and dither colors that
    # fall between steps into a pattern, as the wash's hover showed in game.
    for style in skin.BUTTON_STYLES:
        for state in skin.BUTTON_LOOKS:
            for color in skin.button_look(style, state):
                assert on_steps(color), (style, state, color)
    for fill, edge, icon_alpha in skin.TOGGLE_LOOKS.values():
        assert on_steps(fill) and on_steps(edge) and icon_alpha % skin.STEP == 0
    # Only green and alpha move: red and blue keep EQ Triage's colors exact.
    assert skin.snapped((20, 50, 8, 26)) == (20, 51, 8, 34)
    # And every pixel of the finished art, where the edge blends into the fill and the icons' edges
    # blend into the button: the wash's edge came out at alpha 58 and showed a pattern in game.
    root = everything()
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(root, 'Ui2DAnimation')
    art = {state.text for b in button_controls(root) for state in b.find('ButtonDrawTemplate')} - {
        'TUI_Clear', skin.BUFF_ICONS, skin.ITEM_ICONS}
    assert len(art) > 20
    for name in art:
        off = [p for p in pixels(cut(atlas, anims[name])) if not on_steps(p)]
        assert not off, (name, off[:3])


# XML

@pytest.mark.parametrize('name', list(skin.WINDOW_FILES))
def test_window_files_start_with_the_header_the_client_expects_and_are_ascii_with_crlf(name):
    data = files()[name]
    data.decode('ascii')
    lines = data.split(b'\r\n')
    assert [line.decode() for line in lines[:3]] == list(skin.XML_HEADER)
    assert b'\n' not in data.replace(b'\r\n', b'')
    ET.fromstring(data)


def test_definitions_go_into_the_base_animations_before_its_closing_tag():
    data = files()[skin.ANIMATIONS_FILE].decode('latin-1')
    # The base's own BlueIconBackground goes: the skin redefines it.
    base_head = BASE_ANIMATIONS[:BASE_ANIMATIONS.find('  <Ui2DAnimation item="BlueIconBackground">')]
    assert data.startswith(base_head) and data.endswith('</XML>\r\n')
    assert '\n' not in data.replace('\r\n', '')
    root = parse(skin.ANIMATIONS_FILE)
    assert 'A_Base' in items(root, 'Ui2DAnimation')
    assert skin.FRAME_TEMPLATE in items(root, 'WindowDrawTemplate')


@pytest.mark.parametrize('base', [
    '<XML>\n  <Ui2DAnimation item="A_Base" />\n</XML>\n',
    # All on one line, with a lowercase root like duxaUI's FeedbackWnd.
    '<xml><Ui2DAnimation item="A_Base" /></xml>',
    '<XML>\r\n\t<Ui2DAnimation item="A_Base" />\r\n\t</XML>',
])
def test_definitions_fit_any_base_layout(base):
    text = skin.with_definitions(base, [skin.texture_info('x.tga', 1, 1)])
    root = ET.fromstring(text)
    assert [e.tag for e in root] == ['Ui2DAnimation', 'TextureInfo']
    # Our lines use the file's own line endings.
    if '\r\n' in base:
        assert '\n' not in text.replace('\r\n', '')
    else:
        assert '\r' not in text


def test_a_base_without_a_closing_tag_is_refused():
    with pytest.raises(skin.BuildError, match='no closing'):
        skin.with_definitions('<XML>', [])


def test_the_license_notice_can_stand_in_an_xml_comment():
    notice = skin.LICENSE_NOTICE
    notice.encode('ascii')
    assert '--' not in notice and '<' not in notice and '>' not in notice
    assert 'CC BY-NC-SA 4.0' in notice and 'github.com/CopperGlade/TriageUI' in notice
    ET.fromstring(f'<XML><!-- {notice} --></XML>')


@pytest.mark.parametrize('name', [*skin.WINDOW_FILES, skin.ANIMATIONS_FILE])
def test_every_xml_file_carries_the_license_notice_once(name):
    assert files()[name].decode('latin-1').count(f'<!-- {skin.LICENSE_NOTICE} -->') == 1


def test_the_license_notice_comes_after_every_definition_not_ours():
    base = '<XML>\n  <Ui2DAnimation item="A_Base" />\n</XML>\n'
    text = skin.with_definitions(base, [skin.texture_info('x.tga', 1, 1)], ['<Ui2DAnimation item="A_Kept" />'])
    notice = text.index(skin.LICENSE_NOTICE)
    assert text.index('A_Base') < text.index('A_Kept') < notice < text.index('x.tga')


def test_every_reference_resolves():
    root = everything()
    anims = items(root, 'Ui2DAnimation')
    textures = items(root, 'TextureInfo')
    template = items(root, 'WindowDrawTemplate')[skin.FRAME_TEMPLATE]
    references = [e.text for e in template.find('Border') if not e.tag.startswith('Overlap')]
    references += [e.text for tag in ('GaugeDrawTemplate', 'ButtonDrawTemplate', 'SpellGemDrawTemplate')
                   for t in root.iter(tag) for e in t]
    # The Actions window's tab and page borders, and its tabs' icons.
    frames = items(root, 'FrameTemplate')
    assert {skin.TAB_BORDER, skin.PAGE_BORDER} <= set(frames)
    references += [e.text for t in frames.values() for e in t if not e.tag.startswith('Overlap')]
    references += [e.text for tag in ('TabIcon', 'TabIconActive') for e in root.iter(tag)]
    # Item slots' backgrounds, shown while they're empty.
    references += [e.findtext('Background') for e in root.iter('InvSlot')]
    for tabs in root.iter('TabBox'):
        assert {tabs.findtext(tag) for tag in ('TabBorderTemplate', 'PageBorderTemplate')} <= set(frames)
    # The raid window's list column headings.
    headers = {e.text for e in root.iter('Header')}
    assert headers and headers <= set(frames)
    # The quantity window's slider: its template, and the knob in every state, its track and end caps.
    sliders = items(root, 'SliderDrawTemplate')
    assert {e.findtext('SliderArt') for e in root.iter('Slider')} == {skin.SLIDER_TEMPLATE} <= set(sliders)
    for t in sliders.values():
        references += [e.text for e in t.find('Thumb')]
        references += [t.findtext(part) for part in ('Background', 'EndCapRight', 'EndCapLeft')]
    # The spell and item icons are the stock ones (see the stock names test).
    stock = {skin.BUFF_ICONS, skin.ITEM_ICONS}
    for name in set(references) - stock:
        assert name in anims, name
    references += [e.text for e in root.iter('Animation')]
    for name in set(references) - stock:
        assert name in anims, name
    for anim in anims.values():
        if anim.get('item').startswith('TUI_'):
            texture = anim.find('Frames/Texture').text
            x, y, w, h = rect_of(anim)
            info = textures[texture].find('Size')
            if w == skin.SHOWN_REACH:
                continue  # meant to run past its texture: see the % and divider tests
            assert x + w <= int(info.find('CX').text) and y + h <= int(info.find('CY').text)
    assert template.find('Background').text in textures
    # Everything a window, its clips or its tab pages show is defined earlier in the window's own file.
    for name in skin.WINDOW_FILES:
        file_root, window = screen(name)
        assert window.find('DrawTemplate').text in (skin.FRAME_TEMPLATE, skin.CHAT_TEMPLATE, skin.ITEM_TEMPLATE,
                                                    skin.QUANTITY_TEMPLATE, skin.INSPECT_TEMPLATE)
        defined = set()
        for element in file_root:
            for piece in element.findall('Pieces') + element.findall('Pages'):
                assert piece.text in defined
            if element.get('item'):
                defined.add(element.get('item'))


def test_texture_info_sizes_match_the_textures():
    for name, info in items(parse(skin.ANIMATIONS_FILE), 'TextureInfo').items():
        size = info.find('Size')
        assert decode(files()[name]).size == (int(size.find('CX').text), int(size.find('CY').text))


def test_our_names_never_clash_with_the_stock_skin():
    root = everything()
    ours = [e.get('item') for e in root if e.get('item') and e.get('item') != 'A_Base']
    stock_windows = {'GroupWindow', 'TargetWindow', 'CastingWindow', 'ChatWindow', 'PetInfoWindow', 'SelectorWindow',
                     'BuffWindow', 'ShortDurationBuffWindow', 'PlayerWindow', 'ActionsWindow', 'CastSpellWnd',
                     'HotButtonWnd', 'BreathWindow', 'RaidWindow', 'ContainerWindow', 'MerchantWnd',
                     'ConfirmationDialogBox', 'ItemDisplayWindow', 'QuantityWnd', 'GiveWnd', 'TradeWnd', 'LootWnd',
                     'CompassWindow', 'BankWnd', 'SkillsWindow', 'SpellBookWnd', 'InventoryWindow', 'TrackingWnd',
                     'AAWindow', 'FriendsWindow', 'InspectWnd'}
    # The slot backgrounds the client paints by name are redefined on purpose, and the base's own definitions taken
    # out, so each name is still defined once.
    allowed = stock_windows | {skin.FRAME_TEMPLATE, skin.CHAT_TEMPLATE, skin.FIELD_TEMPLATE, skin.EDIT_TEMPLATE,
                               skin.ITEM_TEMPLATE, skin.QUANTITY_TEMPLATE, skin.INSPECT_TEMPLATE, skin.DIVIDER_TEMPLATE,
                               skin.COMBO_TEMPLATE, *skin.REPLACED_ANIMATIONS}
    assert ours and all(name.startswith('TUI_') or name in allowed or name.endswith('.tga') for name in ours)
    assert len(ours) == len(set(ours))


def test_no_page_lists_a_screen():
    # The game can't load a skin whose tab Page lists a Screen among its pieces, even one defined before it (UIErrors.txt:
    # Couldn't find class:item ... reference in FieldParseItemOfClass(), then the default skin instead), though a
    # window's Screen can list one (the quantity and chat windows' field strips).
    for name in skin.WINDOW_FILES:
        root = parse(name)
        defined = {e.get('item'): e for e in root}
        for page in root.iter('Page'):
            listed = [defined[p.text].tag for p in page.findall('Pieces')]
            assert 'Screen' not in listed, (name, page.get('item'))


def stock_animations():
    for folder in EQ_DIRS:
        path = Path(folder) / 'uifiles' / 'default' / 'EQUI_Animations.xml'
        if folder and path.is_file():
            return set(re.findall(r'<Ui2DAnimation item\s*=\s*"([^"]+)"', path.read_text(encoding='latin-1')))
    pytest.skip('no EverQuest folder with uifiles/default here')


def stock_sidl():
    """The stock SIDL.xml's element types, {name: its definition's text}."""
    for folder in EQ_DIRS:
        path = Path(folder) / 'uifiles' / 'default' / 'SIDL.xml'
        if folder and path.is_file():
            return dict(re.findall(r'<ElementType name="(\w+)">(.*?)</ElementType>', path.read_text(encoding='latin-1'),
                                   re.S))
    pytest.skip('no EverQuest folder with uifiles/default here')


def test_stock_names_we_use_exist_in_the_default_skin():
    stock = stock_animations()
    root = everything()
    used = {e.text for e in root.iter() if e.text and e.text.startswith('A_')} | {skin.BUFF_ICONS}
    assert used and used <= stock
    # And the slot backgrounds we redefine are the stock ones the client paints by name.
    assert set(skin.REPLACED_ANIMATIONS) <= stock


# The windows

def check_inside_frame(name, expected_width=skin.WINDOW_WIDTH, bar=0):
    """Every control within the window's inside: the window within its border, less its title bar, bar tall (none
    unless given)."""
    root, window = screen(name)
    width, height = box(window)[2:]
    assert width == expected_width
    assert window.find('Style_Titlebar').text == ('true' if bar else 'false')
    inner_width, inner_height = width - 2 * skin.BORDER, height - 2 * skin.BORDER - bar
    for element in direct_pieces(root, window):
        if element.findtext('AutoStretch') == 'true':
            continue  # placed by its anchors, as the window's size comes out (see the bag window's tests)
        if element.findtext('ScreenID') in skin.COMPASS_STRIPS:
            continue  # wider than the window, as the stock ones: the game slides them and draws what's inside
        x, y, w, h = box(element)
        assert 0 <= x and x + w <= inner_width and 0 <= y and y + h <= inner_height, element.get('item')
    return root, window


def percent_box(root):
    return box(items(root, 'Screen')['TUI_Target_HPPercent_Clip'])


def test_target_window_shows_name_hp_percent_and_hp_bar():
    # 20% narrower than the other windows, then 10% wider, at the user's requests.
    assert skin.TARGET_WIDTH == 176 == round(skin.WINDOW_WIDTH * 0.8 * 1.1)
    root, window = check_inside_frame(skin.TARGET_FILE, skin.TARGET_WIDTH)
    found = parts(root)
    name, number = found['TUI_Target_Name'], found['TUI_Target_HPLabel']
    assert name.find('EQType').text == '28'
    assert number.find('EQType').text == '29'
    bars = [g for g in root.iter('Gauge') if g.find('ScreenID') is not None]
    assert [g.get('item') for g in bars] == ['TUI_Target_HP']
    assert bars[0].find('EQType').text == '6' and bars[0].find('ScreenID').text == 'TargetHP'
    # No server tick: it's under the mana bar (see the server tick test).
    assert all(g.findtext('EQType') != '24' for g in root.iter('Gauge'))
    # The name and number in the text's color (see the target and casting colors test).
    for element in root.iter('Label'):
        assert rgb(element, 'TextColor') == skin.TEXT_RGB
    assert box(window)[3] == skin.TARGET_HEIGHT
    # The name has the whole first line for long mob names, at the top with the usual padding each side.
    assert box(name)[1] == 0 and box(name)[0] + skin.BORDER == skin.PADDING
    assert skin.TARGET_WIDTH - skin.BORDER - (box(name)[0] + box(name)[2]) == skin.PADDING
    # The number sits straight under the name's line, right-aligned, and the % hugs it.
    assert box(number)[1] == skin.TARGET_LINE2 == box(name)[1] + box(name)[3]
    assert number.find('AlignRight').text == 'true'
    assert box(number)[0] + box(number)[2] == percent_box(root)[0]
    # No typed %: typed text would show even without a target.
    assert all(label.find('Text').text != '%' for label in root.iter('Label'))


def test_target_percent_is_drawn_and_shows_only_with_a_target():
    root = everything()
    clip = items(root, 'Screen')['TUI_Target_HPPercent_Clip']
    digits = box(parts(root)['TUI_Target_HPLabel'])
    x, y, w, h = box(clip)
    # Where Arial's % would be at 12px: 11 wide, 9 tall, plus a row for the half-pixel shift.
    assert (w, h) == (skin.PERCENT_WIDTH, skin.PERCENT_GLYPH_HEIGHT) == (11, 10)
    # Its top 3.5px down the number's line, which the user found perfect after trying 2, 3, 4 and 3 in
    # game. The spot starts at 3 and the glyph is drawn half a pixel down in it.
    assert y == digits[1] + skin.PERCENT_INK_TOP == digits[1] + 3
    assert skin.PERCENT_INK_TOP + skin.PERCENT_SUBPIXEL == 3.5
    # A see-through child window holding one target health gauge with nothing but a fill, which the
    # client draws value x its width: any health covers the clip, no target draws nothing.
    assert clip.find('Style_Transparent').text == 'true'
    (piece,) = clip.findall('Pieces')
    gauge = parts(root)[piece.text]
    assert gauge.find('EQType').text == '6' and gauge.find('ScreenID') is None
    assert box(gauge) == (0, 0, skin.SHOWN_REACH, h)
    assert number(gauge, 'TextOffsetY') >= 8000
    template = gauge.find('GaugeDrawTemplate')
    assert template.find('Background') is None
    fill = items(root, 'Ui2DAnimation')[template.find('Fill').text]
    assert rect_of(fill) == (0, 0, skin.SHOWN_REACH, h) and skin.SHOWN_REACH >= 10000
    assert rgb(gauge, 'FillTint') == skin.TEXT_RGB  # like the number beside it


def test_percent_glyph_is_a_white_percent_sign_alone_at_the_top_left():
    texture = decode(files()[skin.PERCENT_TEXTURE])
    w, h = skin.PERCENT_WIDTH, skin.PERCENT_GLYPH_HEIGHT
    glyph = texture.crop((0, 0, w, h))
    alphas = [a for r, g, b, a in pixels(glyph)]
    # White ink for FillTint to color, anti-aliased, with near-solid strokes.
    assert {(r, g, b) for r, g, b, a in pixels(texture)} == {(255, 255, 255)}
    assert max(alphas) >= 240 and any(0 < a < 240 for a in alphas)
    # Ink in both rings and along the slash: top left, bottom right, and the middle.
    assert glyph.getpixel((1, 1))[3] > 200 and glyph.getpixel((9, 8))[3] > 200
    assert glyph.getpixel((6, 3))[3] > 200 and glyph.getpixel((4, 6))[3] > 200
    # The rings are hollow, and the glyph is the same turned upside down, like Arial's.
    assert glyph.getpixel((2, 2))[3] == 0 and glyph.getpixel((8, 7))[3] == 0
    assert glyph.tobytes() == glyph.transpose(Image.ROTATE_180).tobytes()
    # Drawn half a pixel down: the first and last rows are only partly inked.
    for row in (0, h - 1):
        assert 0 < max(a for *_, a in pixels(glyph.crop((0, row, w, row + 1)))) < 200
    # Nothing else on the texture, so repeating it never shows a second % inside the clip.
    outside = [texture.getpixel((x, y))[3] for x in range(texture.width) for y in range(texture.height)
               if x >= w or y >= h]
    assert set(outside) == {0}


def test_target_second_line_gaps_all_match_the_window_padding_at_100_percent():
    # Window edge to bar, bar to number and % to window edge, with the number and % exactly as wide as
    # 100 and % in font 3 (Arial at 12px). Narrower numbers leave more room before them.
    root = everything()
    found = parts(root)
    name = box(found['TUI_Target_Name'])
    bar = box(found['TUI_Target_HP'])
    number = box(found['TUI_Target_HPLabel'])
    percent = percent_box(root)
    assert skin.BORDER + bar[0] == skin.PADDING
    assert number[0] - (bar[0] + bar[2]) == skin.PADDING
    assert skin.TARGET_WIDTH - skin.BORDER - (percent[0] + percent[2]) == skin.PADDING
    assert bar[0] == name[0] and percent[0] + percent[2] == name[0] + name[2]
    assert (number[2], percent[2]) == (skin.NUMBER_WIDTH, skin.PERCENT_WIDTH) == (21, 11)


def test_bars_are_the_text_color_softened_to_70_percent():
    # The user found a solid bar in the text's color harsh next to the name.
    assert skin.BAR_FILL == (255, 255, 255, 170)  # about 70%, on a 16-bit step
    # (The group window's drawn % is its soft blue: see the group window's test. The inventory's XP and AA bars and
    # their %s are its golden yellow: see its test.)
    group_percents = tuple(f'TUI_GW{n}_HPPercent' for n in range(1, skin.GROUP_SIZE + 1))
    inventory_progress = tuple(f'TUI_IW_{caption}{part}' for _, caption, *_ in skin.INV_PROGRESS
                               for part in ('PercentSign', 'Bar'))
    for g in everything().iter('Gauge'):
        if (g.get('item').startswith('TUI_')
                and not g.get('item').startswith(('TUI_GW_Gauge', 'TUI_GW_PetGauge', 'TUI_PW_', 'TUI_Casting_Gauge',
                                                  'TUI_CSPW_Global_Recast', 'TUI_Breath_Gauge', 'TUI_SBW_Memorize',
                                                  'TUI_SBW_Scribe', *group_percents, *inventory_progress))
                and g.find('GaugeDrawTemplate/Fill') is not None
                and box(g)[2:] != (0, 0)):  # not the hidden ones, which draw nothing
            assert rgb(g, 'FillTint') == skin.TEXT_RGB, g.get('item')


def test_casting_window_is_soft_red_and_target_window_the_text_color():
    # The casting window's text and bar in the soft red, so it stands apart from the target window, whose name,
    # bar, number and drawn % are in the text's color. The user tried them the other way round and came back.
    root = everything()
    found = parts(root)
    assert skin.SPELL_RGB == (232, 128, 128)
    for name in ('TUI_Casting_Prefix', 'TUI_Casting_Spell'):
        assert rgb(found[name], 'TextColor') == skin.SPELL_RGB
    bar = found['TUI_Casting_Gauge']
    assert rgb(bar, 'FillTint') == skin.SPELL_RGB
    assert colors(items(root, 'Ui2DAnimation')[bar.findtext('GaugeDrawTemplate/Fill')]) == {skin.BAR_FILL}
    for name in ('TUI_Target_Name', 'TUI_Target_HPLabel'):
        assert rgb(found[name], 'TextColor') == skin.TEXT_RGB
    assert rgb(found['TUI_Target_HP'], 'FillTint') == rgb(found['TUI_Target_HPPercent'], 'FillTint') == skin.TEXT_RGB


def test_server_tick_is_a_solid_white_line_under_the_mana_bar():
    # Zeal's tick drains to empty when mana comes in, so it sits with mana, where casters look while they med
    # (at the top of the target window players didn't notice it). Solid, in the text's white (the casting bar's
    # soft red hurt the eyes beside the mana bar's blue), with no track, 2px (the user's picks), and only in the
    # player window.
    root = everything()
    ticks = [g for g in root.iter('Gauge') if g.findtext('EQType') == '24']
    assert [g.get('item') for g in ticks] == ['TUI_PW_ZealTick']
    tick = ticks[0]
    assert tick.findtext('ScreenID') == 'ZealTick' and number(tick, 'TextOffsetY') == 8000  # its seconds hidden
    assert rgb(tick, 'FillTint') == skin.TICK_RGB == skin.TEXT_RGB
    anims = items(root, 'Ui2DAnimation')
    assert colors(anims[tick.findtext('GaugeDrawTemplate/Fill')]) == {skin.WHITE}
    assert tick.find('GaugeDrawTemplate/Background') is None
    # As wide as the mana bar, two clear pixels under it (the user's pick: with one, they read as touching).
    player, _ = screen(skin.PLAYER_FILE)
    mana = box(parts(player)['TUI_PW_PlayerMana'])
    assert box(tick) == (mana[0], mana[1] + mana[3] + skin.TICK_GAP, mana[2], skin.TICK_HEIGHT)
    assert skin.TICK_HEIGHT == skin.TICK_GAP == 2
    # The XP/h line's ink two paddings under the tick, as under the sections' bars.
    xp = box(parts(player)['TUI_PW_ExpPerHourCaption'])
    assert 2 * skin.PADDING <= xp[1] + skin.TEXT_INK_TOP - (box(tick)[1] + box(tick)[3]) < 2 * skin.PADDING + 1


def test_target_bar_is_thin_and_level_with_the_health_digits_beside_it():
    found = parts(everything())
    bar = box(found['TUI_Target_HP'])
    number = box(found['TUI_Target_HPLabel'])
    assert bar[3] == skin.TWIN_BAR_HEIGHT == 3 < skin.BAR_HEIGHT
    # 7px down the digits' line: 6px looked slightly high against the number in game.
    assert bar[1] == number[1] + 7


def test_target_bar_has_the_casting_bars_background():
    # The user liked the casting bar's track and asked for the same under the target's bar.
    root = everything()
    anims = items(root, 'Ui2DAnimation')
    gauges = parts(root)
    target = anims[gauges['TUI_Target_HP'].find('GaugeDrawTemplate/Background').text]
    casting = anims[gauges['TUI_Casting_Gauge'].find('GaugeDrawTemplate/Background').text]
    assert colors(target) == colors(casting) == {skin.EDGE_FADED}


def test_group_window_has_every_member_pet_and_health_the_client_looks_for():
    root, _ = check_inside_frame(skin.GROUP_FILE, skin.GROUP_WIDTH)
    by_id = {e.findtext('ScreenID'): e for e in parts(root).values() if e.findtext('ScreenID')}
    for n in range(1, 6):
        assert by_id[f'Gauge{n}'].find('EQType').text == str(10 + n)
        assert by_id[f'PetGauge{n}'].find('EQType').text == str(16 + n)
        number_label = by_id[f'HPLabel{n}']
        assert number_label.find('EQType').text == str(34 + n)
        # "72%" ending at the row's padding: the number right-aligned and a drawn % after it, shown only
        # while the slot has a member (its gauge 10+n above 0).
        clip = items(root, 'Screen')[f'TUI_GW{n}_HPPercent_Clip']
        x, y, w, h = box(clip)
        assert x + w == skin.GROUP_RIGHT and box(number_label)[0] + box(number_label)[2] == x
        assert y == box(number_label)[1] + skin.PERCENT_INK_TOP
        assert number_label.find('AlignRight').text == 'true'
        hidden = parts(root)[clip.find('Pieces').text]
        assert hidden.find('EQType').text == str(10 + n)
        # The name, the number and the drawn % in the mana bar's soft blue (the user's try: the members didn't
        # read well in white). Pets stay grey.
        assert rgb(by_id[f'Gauge{n}'], 'TextColor') == rgb(number_label, 'TextColor') == skin.GROUP_RGB
        assert rgb(hidden, 'FillTint') == skin.GROUP_RGB == skin.MANA_RGB
        assert rgb(by_id[f'PetGauge{n}'], 'TextColor') == skin.PET_RGB
    # The target's and pet's health readouts keep the text's color.
    for name, item in ((skin.TARGET_FILE, 'TUI_Target'), (skin.PET_WINDOW_FILE, 'TUI_PIW')):
        other = parts(screen(name)[0])
        assert rgb(other[f'{item}_HPLabel'], 'TextColor') == rgb(other[f'{item}_HPPercent'], 'FillTint') == skin.TEXT_RGB
    buttons = [e.findtext('ScreenID') for e in root.iter('Button') if e.findtext('ScreenID')]
    # No LFG button: the user didn't want it.
    assert sorted(buttons) == ['DeclineButton', 'DisbandButton', 'FollowButton', 'InviteButton']
    # The client swaps Follow and Decline in where Invite and Disband are.
    invite, disband = box(by_id['InviteButton']), box(by_id['DisbandButton'])
    assert box(by_id['FollowButton']) == invite
    assert box(by_id['DeclineButton']) == disband
    # Side by side, filling the row between the window's padding exactly, as far apart as that padding
    # (the user's rule) and as far below the last pet row.
    assert invite[0] == skin.LEFT and disband[0] + disband[2] == skin.GROUP_RIGHT
    assert disband[0] - (invite[0] + invite[2]) == skin.BUTTON_GAP == skin.PADDING
    # The row splits evenly (were it odd, the second button would take the extra pixel rather than the edge).
    assert (invite[2], disband[2]) == skin.GROUP_BUTTON_WIDTHS == (78, 78)
    last_pet = box(by_id[f'PetGauge{skin.GROUP_SIZE}'])
    assert invite[1] - (last_pet[1] + last_pet[3]) == skin.PADDING


def test_group_members_are_divided_by_the_effects_windows_row_divider():
    # The user asked for the Effects window's dividers here too: always shown, a padding under the pet
    # row above and over the next name's ink.
    root, window = check_inside_frame(skin.GROUP_FILE, skin.GROUP_WIDTH)
    by_id = {e.findtext('ScreenID'): e for e in parts(root).values() if e.findtext('ScreenID')}
    lines = {e.get('item'): e for e in root.iter('StaticAnimation')}
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(everything(), 'Ui2DAnimation')
    group_line, effects_line = (cut(atlas, anims[name]) for name in ('TUI_GroupDivider', 'TUI_RowDivider'))
    assert set(pixels(group_line)) == set(pixels(effects_line)) == {skin.ROW_DIVIDER_RGBA}
    assert group_line.size == (skin.GROUP_CONTENT_WIDTH, 1)
    # As wide as the pet window, and so the hot button window (the user's calls).
    assert skin.GROUP_WIDTH == skin.PET_WIDTH == skin.HOT_WIDTH == 174 == box(window)[2]
    assert sorted(lines) == [f'TUI_GW_Divider{n}' for n in range(2, skin.GROUP_SIZE + 1)]
    for n in range(2, skin.GROUP_SIZE + 1):
        line = lines[f'TUI_GW_Divider{n}']
        assert line.findtext('Animation') == 'TUI_GroupDivider'
        x, y, w, h = box(line)
        above = box(by_id[f'PetGauge{n - 1}'])
        name_top = box(by_id[f'Gauge{n}'])[1]
        assert (x, w, h) == (skin.LEFT, skin.GROUP_CONTENT_WIDTH, 1)
        assert y - (above[1] + above[3]) == skin.PADDING
        assert name_top + skin.TEXT_INK_TOP - (y + h) >= skin.PADDING
        assert name_top + skin.TEXT_INK_TOP - (y + h) < skin.PADDING + 1
    # The HP numbers start blank: a 0 showed in empty slots.
    for n in range(1, skin.GROUP_SIZE + 1):
        assert not by_id[f'HPLabel{n}'].findtext('Text')


def test_group_window_ends_with_invite_and_disband():
    # The style samples that sat under them are gone at the user's request: the window ends a bottom
    # gap under its buttons, and nothing in it is a button the client doesn't know.
    root, window = screen(skin.GROUP_FILE)
    assert all(b.findtext('ScreenID') for b in root.iter('Button'))
    invite = box(parts(root)['TUI_GW_InviteButton'])
    assert box(window)[3] == 2 * skin.BORDER + invite[1] + skin.BUTTON_HEIGHT + skin.BOTTOM_GAP


@pytest.mark.parametrize('style', [s for s in skin.BUTTON_STYLES if s != 'Wash'])
def test_solid_button_styles_lighten_on_hover_darken_when_pressed_and_fade_when_disabled(style):
    # No button uses them now, but BUTTON_STYLE can switch to one.
    fill, edge, _ = skin.BUTTON_STYLES[style]
    looks = {state: skin.button_look(style, state) for state in skin.BUTTON_LOOKS}
    assert looks['Normal'] == (fill, edge) and fill[3] == 255
    assert sum(looks['Flyby'][0][:3]) > sum(fill[:3]) > sum(looks['Pressed'][0][:3])
    assert looks['Disabled'][0][3] < 255


def test_group_members_and_pets_each_have_a_thin_solid_bar_in_their_names_color():
    # A member is their name and health % on one line with a thin bar under the name, like their pet's (the
    # user loved the blue and grey lines' contrast and asked for it; members had no bar before). Both bars
    # are solid in their names' colors, with no track, and end where the pet window's bar does (the user's
    # pick; the target's before). The pet's line a padding under the member's bar, to its name's ink.
    root = everything()
    anims = items(root, 'Ui2DAnimation')
    pet_window = rect_of(anims[parts(root)['TUI_PIW_PetHPGauge'].find('GaugeDrawTemplate/Fill').text])[2]
    for n in range(1, skin.GROUP_SIZE + 1):
        member, pet = parts(root)[f'TUI_GW_Gauge{n}'], parts(root)[f'TUI_GW_PetGauge{n}']
        for gauge, names_rgb in ((member, skin.GROUP_RGB), (pet, skin.PET_RGB)):
            template = gauge.find('GaugeDrawTemplate')
            assert [e.tag for e in template] == ['Fill']
            fill = anims[template.findtext('Fill')]
            assert colors(fill) == {skin.WHITE} and rect_of(fill)[3] == skin.PET_BAR_HEIGHT
            assert rgb(gauge, 'FillTint') == rgb(gauge, 'TextColor') == names_rgb
            bar = rect_of(fill)[2]
            assert box(gauge)[0] + number(gauge, 'GaugeOffsetX') + bar == skin.LEFT + pet_window
        assert number(member, 'GaugeOffsetX') == 0
        assert number(member, 'GaugeOffsetY') == skin.TEXT_HEIGHT + skin.PET_BAR_GAP == 15
        assert box(member)[3] == number(member, 'GaugeOffsetY') + skin.PET_BAR_HEIGHT
        assert box(pet)[1] + skin.CAPTION_INK_TOP - (box(member)[1] + box(member)[3]) == skin.PADDING
    assert skin.GROUP_BAR_WIDTH == skin.PIW_BAR_WIDTH == pet_window
    assert skin.MEMBER_PITCH == 46


def test_group_names_are_the_gauges_own_text_and_pets_are_big_full_rows_to_click():
    root, _ = screen(skin.GROUP_FILE)
    gauges = {e.findtext('ScreenID'): e for e in root.iter('Gauge') if e.findtext('ScreenID')}
    rows = []
    for n in range(1, 6):
        member, pet = gauges[f'Gauge{n}'], gauges[f'PetGauge{n}']
        assert number(member, 'TextOffsetY') == 0 and number(pet, 'TextOffsetY') == 0
        assert number(pet, 'TextOffsetX') == skin.PET_INDENT
        assert rgb(pet, 'TextColor') == skin.PET_RGB
        # The whole row is the click target: as wide as a member's and tall enough for a line of text,
        # in font 2 so the window is less tall (the user's call).
        assert box(pet)[2] == box(member)[2] == skin.GROUP_CONTENT_WIDTH
        assert box(pet)[3] >= skin.PET_TEXT_HEIGHT
        assert pet.findtext('Font') == '2' and member.findtext('Font') == str(skin.TEXT_FONT)
        # Its bar a pixel under its name's line (the user asked for the extra pixel).
        assert number(pet, 'GaugeOffsetY') == skin.PET_TEXT_HEIGHT + 1 == skin.PET_TEXT_HEIGHT + skin.PET_BAR_GAP
        rows += [box(member), box(pet)]
    for i, (x, y, w, h) in enumerate(rows):
        for (x2, y2, w2, h2) in rows[i + 1:]:
            assert y + h <= y2 or y2 + h2 <= y


def test_casting_window_shows_casting_the_spell_and_its_progress():
    root, _ = check_inside_frame(skin.CASTING_FILE, skin.TARGET_WIDTH)
    found = parts(root)
    prefix, spell = found['TUI_Casting_Prefix'], found['TUI_Casting_Spell']
    assert prefix.find('Text').text == 'Casting:' and prefix.find('EQType') is None
    assert spell.find('EQType').text == '134'
    # The whole line in one color (see the target and casting colors test).
    assert rgb(spell, 'TextColor') == rgb(prefix, 'TextColor')
    # The spell name follows "Casting:" and a space, on the same line, to the window's padding.
    assert box(prefix)[0] == skin.LEFT and box(spell)[0] == box(prefix)[0] + box(prefix)[2] == skin.LEFT + 50
    assert box(prefix)[1] == box(spell)[1] == 0
    assert box(spell)[0] + box(spell)[2] == skin.TARGET_RIGHT
    gauge = found['TUI_Casting_Gauge']
    assert gauge.find('EQType').text == '7' and gauge.find('ScreenID').text == 'Gauge'


def test_casting_window_is_the_target_windows_size_with_a_full_width_bar():
    # The same size as the target window, the bar at the height of its health bar, as if there were text on
    # the second line to center it on, but across the whole width (the user's request).
    root = everything()
    cast = parts(root)['TUI_Casting_Gauge']
    health = box(parts(root)['TUI_Target_HP'])
    assert box(cast)[1] == health[1] and box(cast)[3] == health[3]
    assert box(cast)[0] == skin.LEFT and box(cast)[0] + box(cast)[2] == skin.TARGET_RIGHT
    assert box(screen(skin.CASTING_FILE)[1])[2:] == box(screen(skin.TARGET_FILE)[1])[2:]
    assert box(screen(skin.TARGET_FILE)[1])[3] == skin.TARGET_HEIGHT


def test_air_window_is_the_casting_windows_twin_in_soft_cyan():
    # The user's picks: "Air Remaining" over a full-width bar, the casting window's size so the two line up when
    # stacked, both in a soft cyan. The game gives skins no number for the air left.
    root, window = check_inside_frame(skin.BREATH_FILE, skin.TARGET_WIDTH)
    assert box(window)[2:] == box(screen(skin.CASTING_FILE)[1])[2:]
    assert window.findtext('Text') == 'Air Remaining'
    assert window.findtext('TooltipReference') == 'The Breath Meter'  # the default skin's
    found = parts(root)
    caption, bar = found['TUI_Breath_Caption'], found['TUI_Breath_Gauge']
    assert caption.findtext('Text') == 'Air Remaining' and caption.find('EQType') is None
    assert box(caption)[:2] == (skin.LEFT, 0)
    # The stock window's gauge, where the casting bar is, with its own text hidden.
    assert bar.findtext('EQType') == '8' and bar.findtext('ScreenID') == 'Gauge'
    assert box(bar) == box(parts(everything())['TUI_Casting_Gauge'])
    assert number(bar, 'TextOffsetY') > box(bar)[3]
    assert skin.AIR_RGB == (128, 216, 232)
    assert rgb(caption, 'TextColor') == rgb(bar, 'FillTint') == skin.AIR_RGB
    anims = items(everything(), 'Ui2DAnimation')
    assert colors(anims[bar.findtext('GaugeDrawTemplate/Fill')]) == {skin.BAR_FILL}
    assert colors(anims[bar.findtext('GaugeDrawTemplate/Background')]) == {skin.EDGE_FADED}


def test_pet_window_is_the_target_windows_shape_with_its_commands():
    # As wide as the hot button window (the user's call), two pixels narrower than the target window: its
    # readout sits that much further left, and its bar is that much shorter.
    assert skin.PET_WIDTH == skin.HOT_WIDTH == 174
    shift = skin.PET_WIDTH - skin.TARGET_WIDTH
    assert shift == -2
    root, window = check_inside_frame(skin.PET_WINDOW_FILE, skin.PET_WIDTH)
    everything_root = everything()
    found = parts(root)
    by_id = {e.findtext('ScreenID'): e for e in found.values() if e.findtext('ScreenID')}
    # Your pet's gauge: its own text is the pet's name ("No Pet" until the client sets it) on the first
    # line, and its bar where the target window's is, shorter like the window.
    health = by_id['PetHPGauge']
    assert health.find('EQType').text == '16'
    assert (number(health, 'TextOffsetX'), number(health, 'TextOffsetY')) == (0, 0)
    assert health.find('Text').text == 'No Pet'
    target_bar = box(parts(everything_root)['TUI_Target_HP'])
    x, y, w, h = box(health)
    assert (x + number(health, 'GaugeOffsetX'), y + number(health, 'GaugeOffsetY')) == target_bar[:2]
    assert (w, h - number(health, 'GaugeOffsetY')) == (target_bar[2] + shift, target_bar[3])
    # Its HP number and drawn % on the target's line, ending at the window's padding; at 100% the bar
    # ends a padding's width before the number, as in the target window. The % shows only while you
    # have a pet.
    number_label = by_id['PIW_PetHPLabel']
    assert number_label.find('EQType').text == '69'
    target_number = box(parts(everything_root)['TUI_Target_HPLabel'])
    assert box(number_label) == (target_number[0] + shift, *target_number[1:])
    assert box(number_label)[0] - (x + w) == skin.PADDING
    clips = items(root, 'Screen')
    percent = box(clips['TUI_PIW_HPPercent_Clip'])
    target_percent = box(items(everything_root, 'Screen')['TUI_Target_HPPercent_Clip'])
    assert percent == (target_percent[0] + shift, *target_percent[1:])
    assert skin.PET_WIDTH - skin.BORDER - (percent[0] + percent[2]) == skin.PADDING
    hidden = found[clips['TUI_PIW_HPPercent_Clip'].find('Pieces').text]
    assert hidden.find('EQType').text == '16' and hidden.find('ScreenID') is None


def test_pet_commands_are_three_columns_of_related_pairs():
    # The user paired related commands and wanted them to read together: each column is a pair.
    root, window = screen(skin.PET_WINDOW_FILE)
    visible = [b for b in root.iter('Button') if box(b)[2:] != (0, 0)]
    labels = {screen_id: label for column in skin.PET_COLUMNS for screen_id, label, _ in column}
    texts = [[labels[b.findtext('ScreenID')] for b in visible if box(b)[0] == x]
             for x in sorted({box(b)[0] for b in visible})]
    assert texts == [['Attack', 'Back'], ['Guard', 'Follow'], ['Taunt', 'Dismiss']]
    # Each shows its own label's art.
    for b in visible:
        label = labels[b.findtext('ScreenID')]
        assert b.findtext('ButtonDrawTemplate/Normal') == f'TUI_{skin.button_art(*box(b)[2:], label, "Normal")}'
    w, top = skin.PET_BUTTON_WIDTH, skin.PET_BUTTONS_TOP
    assert w == 50  # the hot button window's row, split evenly
    xs = sorted({box(b)[0] for b in visible})
    # Between columns, between a pair's buttons, and under the health line, the window's side padding
    # (the user's rule), the columns even and filling the name line's width exactly. The health line's
    # lowest ink is the HP number and %, whose bottom is the drawn %'s.
    assert skin.BUTTON_GAP == skin.PET_PAIR_GAP == skin.BUTTON_ROW_GAP == skin.PADDING == 6
    percent = box(items(root, 'Screen')['TUI_PIW_HPPercent_Clip'])
    assert top - (percent[1] + percent[3]) == skin.PADDING
    health = parts(root)['TUI_PIW_PetHPGauge']
    assert top > box(health)[1] + box(health)[3] + skin.PADDING
    assert xs[0] == skin.LEFT and xs[-1] + w == skin.PET_RIGHT
    assert [b - (a + w) for a, b in zip(xs, xs[1:])] == [skin.PADDING] * 2
    assert {box(b)[1] for b in visible} == {top, top + skin.BUTTON_HEIGHT + skin.PET_PAIR_GAP}
    assert all(box(b)[2:] == (w, skin.BUTTON_HEIGHT) for b in visible)
    # The default skin's tooltips, and the ScreenIDs the client looks for.
    by_id = {b.findtext('ScreenID'): b for b in visible}
    for column in skin.PET_COLUMNS:
        for screen_id, text, tooltip in column:
            assert by_id[screen_id].findtext('TooltipReference') == tooltip
    # "Go Away" was a bit too wide for the button in game, so it's "Dismiss" (fitting is tested with
    # the lettering).
    assert 'Dismiss' in labels.values()
    assert box(window)[3] == 2 * skin.BORDER + top + 2 * skin.BUTTON_HEIGHT + skin.PET_PAIR_GAP + skin.BOTTOM_GAP


def test_pet_and_group_windows_are_as_wide_as_the_hot_button_window():
    # The user's call, like the Actions window's, so they line up stacked. The row inside splits evenly for the
    # pet window's three columns and the group window's two buttons.
    hot = box(screen(skin.HOTBUTTON_FILE)[1])[2]
    assert hot == skin.HOT_WIDTH == 174
    for name in (skin.PET_WINDOW_FILE, skin.GROUP_FILE):
        assert box(screen(name)[1])[2] == hot, name
    content = hot - 2 * skin.PADDING
    assert 3 * skin.PET_BUTTON_WIDTH + 2 * skin.BUTTON_GAP == content
    assert sum(skin.GROUP_BUTTON_WIDTHS) + skin.BUTTON_GAP == content


def test_sit_is_hidden_but_still_there_for_the_client():
    # Nobody uses Sit (the user), but the client looks up every command button: it's there with no
    # size, no text and clear art.
    root, window = screen(skin.PET_WINDOW_FILE)
    sit = [b for b in root.iter('Button') if b.findtext('ScreenID') == 'SitButton']
    assert len(sit) == 1
    assert box(sit[0])[2:] == (0, 0) and not sit[0].findtext('Text')
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(everything(), 'Ui2DAnimation')
    for state in sit[0].find('ButtonDrawTemplate'):
        assert {a for *_, a in pixels(cut(atlas, anims[state.text]))} == {0}
    # Every command the default pet window has is there, seen or not.
    ids = {b.findtext('ScreenID') for b in root.iter('Button')}
    assert ids == {'AttackButton', 'BackButton', 'GuardButton', 'FollowButton', 'TauntButton', 'LostButton',
                   'SitButton'}


def anchors(element):
    return tuple(number(element, f'{side}AnchorOffset') for side in ('Left', 'Top', 'Right', 'Bottom'))


def test_chat_window_has_a_thin_title_bar_to_drag_by_and_resizes():
    # A sizable window with no title bar can't be dragged in this client (the corner grip never moved it;
    # poweroftwo's readme says the same of its title-less chat window), so the user asked for a really
    # thin header, with no name on it (everyone knows which window they chat in) and no minimize box. Its only
    # box is the close box, the X (the user's pick), as the stock chat windows have one.
    root, window = screen(skin.CHAT_FILE)
    assert window.get('item') == 'ChatWindow'
    assert window.find('Style_Titlebar').text == 'true'
    assert window.find('Style_Closebox').text == 'true' and window.find('Style_Minimizebox').text == 'false'
    assert window.find('Style_Sizable').text == 'true' and window.find('Style_Border').text == 'true'
    assert window.find('DrawTemplate').text == skin.CHAT_TEMPLATE
    # The client names each chat window itself and writes the name on the bar in its own color: neither a
    # panel-colored TextColor nor one with alpha 0 hid it in game, so it stays, in font 2 (the user's pick
    # after 0).
    assert window.find('Text') is None and window.find('TextColor') is None
    assert window.findtext('Font') == str(skin.TITLE_FONT) == '2'
    assert box(window)[2:] == skin.CHAT_SIZE
    # No corner grip any more.
    assert not [e for e in root if e.get('item', '').startswith('TUI_CW_GripDot')]


def test_chat_text_and_input_stretch_with_the_window_and_never_overlap():
    root, window = screen(skin.CHAT_FILE)
    found = {e.findtext('ScreenID') or e.get('item'): e for e in direct_pieces(root, window)}
    output, field = found['CWChatOutput'], found['CWChatInput']
    assert output.tag == 'STMLbox' and field.tag == 'Editbox'
    for control in (output, field):
        assert control.find('AutoStretch').text == 'true'
        assert control.find('RightAnchorToLeft').text == 'false' and control.find('BottomAnchorToTop').text == 'false'
        assert control.find('Style_Border').text == 'false'
    # The chat: the window's padding on three sides, above the input line and a gap; a scrollbar; no
    # panel of its own on top of the window's.
    assert anchors(output) == (skin.LEFT, skin.LEFT, skin.LEFT, skin.LEFT + skin.INPUT_HEIGHT + skin.INPUT_GAP)
    assert output.find('TopAnchorToTop').text == 'true'
    assert output.find('Style_VScroll').text == 'true' and output.find('Style_Transparent').text == 'true'
    assert output.find('DrawTemplate').text == skin.FRAME_TEMPLATE
    # The input line: a strip INPUT_HEIGHT tall along the bottom (its top measured up from the bottom),
    # across the whole width, drawn by a child window's background.
    strip = found['TUI_CW_InputStrip']
    assert strip.tag == 'Screen'
    assert anchors(strip) == (skin.LEFT, skin.LEFT + skin.INPUT_HEIGHT, skin.LEFT, skin.LEFT)
    assert strip.find('TopAnchorToTop').text == 'false' and strip.find('AutoStretch').text == 'true'
    # Its background and its 1px outline both drawn.
    assert strip.find('Style_Transparent').text == 'false' and strip.find('Style_Border').text == 'true'
    assert strip.find('DrawTemplate').text == skin.FIELD_TEMPLATE
    # The input box on it, see-through, inset FIELD_PADDING left and right (it has no padding setting of
    # its own), as tall as the strip: the user wanted the text as far in from the sides as from the top.
    l, t, r, b = anchors(strip)
    assert anchors(field) == (l + skin.FIELD_PADDING, t, r + skin.FIELD_PADDING, b)
    assert field.find('TopAnchorToTop').text == 'false'
    assert field.find('Style_Transparent').text == 'true'
    # The box draws nothing of its own: a clear background and border (with the field's template the user
    # saw a second box under it in game), so the strip is the only field.
    assert field.find('DrawTemplate').text == skin.EDIT_TEMPLATE
    clear = items(everything(), 'WindowDrawTemplate')[skin.EDIT_TEMPLATE]
    assert clear.findtext('Background') == skin.GUTTER_TEXTURE
    assert {e.text for e in clear.find('Border') if e.tag in skin.BORDER_PIECES} == {'TUI_Clear'}
    assert {p[3] for p in pixels(decode(files()[skin.GUTTER_TEXTURE]))} == {0}
    # Drawn after the strip, so the text is on top of it.
    order = [p.text for p in window.findall('Pieces')]
    assert order.index('TUI_CW_InputStrip') < order.index('TUI_CW_ChatInput')


def test_chat_title_bar_is_a_thin_strip_of_the_panel_with_a_divider_under_it():
    # The chat frame is the usual one plus its own title pieces: TITLE_HEIGHT tall, the panel's color, a
    # row divider along the bottom to show where to drag (the stock rounded title pieces are opaque
    # rectangles, so the client draws the bar inside the border, under the top edge).
    templates = items(everything(), 'WindowDrawTemplate')
    chat, usual = templates[skin.CHAT_TEMPLATE], templates[skin.FRAME_TEMPLATE]
    assert chat.findtext('Background') == usual.findtext('Background') == skin.BACKGROUND_TEXTURE
    assert [(e.tag, e.text) for e in chat.find('Border')] == [(e.tag, e.text) for e in usual.find('Border')]
    assert {chat.findtext(f'Titlebar/{side}') for side in ('Left', 'Middle', 'Right')} == {'TUI_TitleBar'}
    assert {usual.findtext(f'Titlebar/{side}') for side in ('Left', 'Middle', 'Right')} == {
        f'A_RoundedFrameTitle{side}' for side in ('Left', 'Middle', 'Right')}
    anims = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')
    bar = cut(decode(files()[skin.PIECES_TEXTURE]), anims['TUI_TitleBar'])
    # 10px at the user's request (8 first, then 3 and 6, back to 8 for the font 2 name, then 2px taller;
    # the stock bar is 14).
    assert bar.size == (skin.TITLE_PIECE_WIDTH, skin.TITLE_HEIGHT) and skin.TITLE_HEIGHT == 10
    rows = [set(bar.getpixel((x, y)) for x in range(bar.width)) for y in range(bar.height)]
    assert rows[:-1] == [{skin.PANEL_RGBA}] * (skin.TITLE_HEIGHT - 1)
    assert rows[-1] == {skin.TITLE_DIVIDER_RGBA} == {skin.snapped(skin.over(skin.ROW_DIVIDER_RGBA, 1, skin.PANEL_RGBA))}
    assert skin.TITLE_DIVIDER_RGBA[3] == 255 and skin.TITLE_DIVIDER_RGBA != skin.PANEL_RGBA


def test_chat_close_box_is_an_x_like_the_scrollbar_arrows():
    # The user's pick: an X, the bar being too thin for the Close button of the item and quantity windows. In the
    # arrows' soft white at their alpha per state, brighter hovered and pressed, pressed-and-hovered looking pressed.
    chat = items(everything(), 'WindowDrawTemplate')[skin.CHAT_TEMPLATE]
    close = chat.find('CloseBox')
    assert [(e.tag, e.text) for e in close] == [(state, f'TUI_ChatClose{skin.BUTTON_ART[state]}')
                                                for state in skin.BUTTON_STATES]
    anims = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')
    atlas = decode(files()[skin.PIECES_TEXTURE])
    # The game draws it at its art's size, its top CLOSE_BOX_TOP under the bar's (see the item window): a square
    # as far above the divider, so the X is centered down the bar above it.
    size = skin.CHAT_CLOSE_SIZE
    assert skin.CLOSE_BOX_TOP + size + skin.CLOSE_BOX_TOP + skin.DIVIDER_HEIGHT == skin.TITLE_HEIGHT and size == 7
    for look, alpha in skin.SCROLL_LOOKS.items():
        art = cut(atlas, anims[f'TUI_ChatClose{look}'])
        assert art.size == (size, size)
        assert {p[:3] for p in pixels(art) if p[3]} == {(255, 255, 255)}
        assert max(p[3] for p in pixels(art)) == alpha
        # An X: both diagonals through the middle, the same mirrored either way, and clear between its arms.
        middle = size // 2
        assert art.getpixel((middle, middle))[3] == alpha
        for x in range(size):
            for y in range(size):
                assert art.getpixel((x, y)) == art.getpixel((size - 1 - x, y)) == art.getpixel((x, size - 1 - y))
        assert art.getpixel((middle, 0))[3] == art.getpixel((0, middle))[3] == 0


def test_input_field_is_a_plain_strip_darker_than_the_panel_with_a_faint_outline():
    # The user wanted it simple, darker than the window rather than lighter, tall enough for letters, and
    # outlined with slight contrast to the colors on either side.
    root = everything()
    template = items(root, 'WindowDrawTemplate')[skin.FIELD_TEMPLATE]
    assert template.find('Background').text == skin.FIELD_TEXTURE
    (field,) = set(pixels(decode(files()[skin.FIELD_TEXTURE])))
    assert field == skin.FIELD_RGBA
    # A near-black navy (the panel's hue at half brightness falls between the 16-bit steps), laid over
    # the panel: darker, not lighter or grey.
    assert field[2] > field[0] == field[1] and 0 < field[3] < 255
    over_panel = skin.over(field, 1, skin.PANEL_RGBA)
    assert sum(over_panel[:3]) < sum(skin.PANEL_RGBA[:3]) and over_panel[3] == 255
    # Every side and corner of its border is one pixel of the window edge's color: lighter than both the
    # field inside it and the panel outside it.
    edges = {e.text for e in template.find('Border') if not e.tag.startswith('Overlap')}
    assert edges == {'TUI_FieldEdge'}
    edge = items(root, 'Ui2DAnimation')['TUI_FieldEdge']
    assert rect_of(edge)[2:] == (1, 1) and colors(edge) == {skin.EDGE_FADED}
    line = skin.over(skin.EDGE_FADED, 1, skin.PANEL_RGBA)
    assert sum(line[:3]) > sum(skin.PANEL_RGB) > sum(over_panel[:3])
    assert skin.INPUT_HEIGHT == 20


def test_scrollbar_is_slim_chevrons_and_a_thin_thumb_on_a_clear_track():
    root = everything()
    anims = items(root, 'Ui2DAnimation')
    atlas = decode(files()[skin.PIECES_TEXTURE])
    for name in (skin.FRAME_TEMPLATE, skin.FIELD_TEMPLATE):
        vsb = items(root, 'WindowDrawTemplate')[name].find('VSBTemplate')
        assert vsb.find('MiddleTextureInfo').text == skin.GUTTER_TEXTURE
        for way in ('UpButton', 'DownButton'):
            states = vsb.find(way)
            assert [e.tag for e in states] == list(skin.BUTTON_STATES)
            for state in states:
                assert cut(atlas, anims[state.text]).size == (skin.SCROLL_WIDTH, skin.SCROLL_BUTTON_HEIGHT)
        thumb = [cut(atlas, anims[vsb.find(f'Thumb/{part}').text]) for part in ('Top', 'Middle', 'Bottom')]
        assert [piece.size for piece in thumb] == [(skin.SCROLL_WIDTH, skin.THUMB_CAP), (skin.SCROLL_WIDTH, 1),
                                                   (skin.SCROLL_WIDTH, skin.THUMB_CAP)]
    assert set(pixels(decode(files()[skin.GUTTER_TEXTURE]))) == {(255, 255, 255, 0)}
    # The thumb's middle: THUMB_WIDTH of soft white, centered, clear either side.
    middle = [a for r, g, b, a in pixels(cut(atlas, anims['TUI_ThumbMiddle']))]
    inked = [x for x, a in enumerate(middle) if a]
    assert middle[inked[0]:inked[-1] + 1] == [skin.THUMB_ALPHA] * skin.THUMB_WIDTH
    assert inked[0] == skin.SCROLL_WIDTH - 1 - inked[-1]
    # The arrows: a chevron pointing the right way, brighter when hovered and pressed.
    up = cut(atlas, anims['TUI_ScrollUpNormal'])
    down = cut(atlas, anims['TUI_ScrollDownNormal'])
    assert up.transpose(Image.FLIP_TOP_BOTTOM).tobytes() == down.tobytes()
    tip = (skin.SCROLL_WIDTH // 2, skin.SCROLL_BUTTON_HEIGHT // 2 - 2)
    assert up.getpixel(tip)[3] > up.getpixel((skin.SCROLL_WIDTH // 2, skin.SCROLL_BUTTON_HEIGHT // 2 + 2))[3]
    brightest = {state: max(a for *_, a in pixels(cut(atlas, anims[f'TUI_ScrollUp{state}'])))
                 for state in skin.SCROLL_LOOKS}
    assert brightest['Disabled'] < brightest['Normal'] < brightest['Flyby'] < brightest['Pressed']


def selector_toggles(root, window):
    """The selector's visible toggles, in order (not the hidden Help button)."""
    return [t for t in (parts(root)[p.text] for p in window.findall('Pieces')) if box(t)[2:] != (0, 0)]


def test_selector_has_every_toggle_the_client_looks_for_with_the_default_tooltips():
    root, window = screen(skin.SELECTOR_FILE)
    toggles = selector_toggles(root, window)
    assert [(t.findtext('ScreenID'), t.findtext('TooltipReference')) for t in toggles] == [
        ('SELW_OptionsToggleButton', 'Options'), ('SELW_InventoryToggleButton', 'Inventory'),
        ('SELW_ActionsToggleButton', 'Actions'), ('SELW_FriendsToggleButton', 'Friends'),
        ('SELW_HotboxToggleButton', 'Hotbuttons'), ('SELW_CastSpellToggleButton', 'Spells'),
        ('SELW_PetInfoToggleButton', 'Pet Info'), ('SELW_BuffToggleButton', 'Effects')]
    # Toggles: pressed while their window is open.
    assert {t.findtext('Style_Checkbox') for t in toggles} == {'true'}
    assert {t.find('Text') for t in toggles} == {None}
    # Help is gone at the user's request, but the client looks it up: there with no size and clear art.
    hidden = [b for b in root.iter('Button') if box(b)[2:] == (0, 0)]
    assert [b.findtext('ScreenID') for b in hidden] == ['SELW_HelpToggleButton']
    assert {s.text for s in hidden[0].find('ButtonDrawTemplate')} == {'TUI_Clear'}


def test_selector_is_one_row_of_toggles_spaced_by_the_window_padding():
    # The user's standard: 6px between everything, and from the window's edge.
    root, window = check_inside_frame(skin.SELECTOR_FILE, skin.SELECTOR_WIDTH)
    width, height = box(window)[2:]
    toggles = [box(t) for t in selector_toggles(root, window)]
    assert all((w, h) == (skin.TOGGLE_SIZE, skin.TOGGLE_SIZE) for _, _, w, h in toggles)
    first, last = toggles[0], toggles[-1]
    assert skin.BORDER + first[0] == skin.PADDING == width - (skin.BORDER + last[0] + last[2])
    assert {skin.BORDER + y for _, y, _, _ in toggles} == {skin.PADDING}
    assert height - (skin.BORDER + first[1] + first[3]) == skin.PADDING
    assert [b[0] - (a[0] + a[2]) for a, b in zip(toggles, toggles[1:])] == [skin.PADDING] * (len(toggles) - 1)


def test_selector_icons_are_distinct_centered_and_light_up_when_hovered_or_open():
    root = everything()
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(root, 'Ui2DAnimation')
    toggles = selector_toggles(*screen(skin.SELECTOR_FILE))
    plain = {state: as_image(skin.snapped_art(skin.panel_texture(skin.TOGGLE_SIZE, skin.TOGGLE_SIZE, *look[:2])))
             for state, look in skin.TOGGLE_LOOKS.items()}
    inset = (skin.TOGGLE_SIZE - skin.ICON_SIZE) // 2
    icon_box = (inset, inset, inset + skin.ICON_SIZE, inset + skin.ICON_SIZE)
    normals = set()
    for toggle in toggles:
        art = {state.tag: cut(atlas, anims[state.text]) for state in toggle.find('ButtonDrawTemplate')}
        # Never disabled, as in the default skin: Disabled shows the Normal art.
        assert art['Disabled'].tobytes() == art['Normal'].tobytes()
        for state in skin.TOGGLE_LOOKS:
            # The icon stays inside its centered 16px square: outside it, the art is the plain button.
            outside = Image.new('RGBA', art[state].size)
            outside.paste(art[state])
            outside.paste((0, 0, 0, 0), icon_box)
            empty = plain[state].copy()
            empty.paste((0, 0, 0, 0), icon_box)
            assert outside.tobytes() == empty.tobytes(), (toggle.get('item'), state)
        # The icon is dimmer while closed; open is lighter than hovered, and lighter still hovered.
        ink = {state: max(sum(p[:3]) * p[3] for p in pixels(art[state].crop(icon_box))) for state in art}
        assert ink['Normal'] < ink['Flyby']
        middle = (1, skin.TOGGLE_SIZE // 2)
        lightness = {state: sum(art[state].getpixel(middle)[:3]) for state in skin.TOGGLE_LOOKS}
        assert lightness['Flyby'] < lightness['Pressed'] < lightness['PressedFlyby']
        normals.add(art['Normal'].tobytes())
    assert len(normals) == len(skin.SELECTOR_BUTTONS)


# The Actions window

# Every control the stock Actions window has, by page: the client looks each up by ScreenID.
STOCK_ACTIONS = {
    'ActionsMainPage': ['AMP_WhoButton', 'AMP_InviteButton', 'AMP_FollowButton', 'AMP_DisbandButton', 'AMP_CampButton',
                        'AMP_SitButton', 'AMP_StandButton', 'AMP_RunButton', 'AMP_WalkButton'],
    'ActionsAbilitiesPage': [f'AAP_{n}AbilityButton' for n in ('First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth')],
    'ActionsCombatPage': ['ACP_MeleeAttackButton', 'ACP_RangeAttackButton'] + [
        f'ACP_{n}AbilityButton' for n in ('First', 'Second', 'Third', 'Fourth')],
    'ActionsSocialsPage': ['ASP_SocialPageLeftButton', 'ASP_CurrentSocialPageLabel', 'ASP_SocialPageRightButton'] + [
        f'ASP_SocialButton{n}' for n in range(1, 13)],
}


def actions_pages():
    """The Actions window file, and each page's ScreenID → its parts by ScreenID, in order."""
    root, window = screen(skin.ACTIONS_FILE)
    defined, pages = parts(root), items(root, 'Page')
    tabs = direct_pieces(root, window)[0]
    return root, window, tabs, {pages[p.text].findtext('ScreenID'): {
        defined[piece.text].findtext('ScreenID'): defined[piece.text] for piece in pages[p.text].findall('Pieces')}
        for p in tabs.findall('Pages')}


def test_actions_window_keeps_every_control_the_client_looks_for_on_its_stock_page():
    root, window, tabs, pages = actions_pages()
    assert window.get('item') == 'ActionsWindow' and window.findtext('Style_Titlebar') == 'false'
    assert tabs.tag == 'TabBox' and tabs.findtext('ScreenID') == 'ACTW_ActionsSubwindows'
    # The stock pages, in the stock order, each holding its stock controls.
    assert list(pages) == list(STOCK_ACTIONS)
    for page, controls in STOCK_ACTIONS.items():
        assert sorted(pages[page]) == sorted(controls), page
    # Who and Disband, and the socials' bottom three rows (4, 5, 6, 10, 11 and 12), are gone at the user's
    # request, but the client looks them up: no size, clear art.
    hidden = [b for b in root.iter('Button') if box(b)[2:] == (0, 0)]
    assert [b.findtext('ScreenID') for b in hidden] == ['AMP_WhoButton', 'AMP_DisbandButton'] + [
        f'ASP_SocialButton{n}' for n in (4, 5, 6, 10, 11, 12)]
    assert {s.text for b in hidden for s in b.find('ButtonDrawTemplate')} == {'TUI_Clear'}


# The border pieces the stock templates have: the tab border has no bottom row, the page border all twelve.
STOCK_TAB_BORDER = ['TopLeft', 'Top', 'TopRight', 'RightTop', 'Right', 'RightBottom', 'LeftTop', 'Left', 'LeftBottom']
STOCK_PAGE_BORDER = ['TopLeft', 'Top', 'TopRight', 'RightTop', 'Right', 'RightBottom', 'BottomRight', 'Bottom',
                     'BottomLeft', 'LeftTop', 'Left', 'LeftBottom']


def tab_box_layout(tabs, pages):
    """Where the game puts a tab box's tabs and pages, worked out from its border templates' pieces the way
    eqgame.exe's tab box code does it (read after the first build crashed the game; see skin.TAB_BORDER).

    Returns each tab's icon spot (x, y) while its page is open (a closed page's is TAB_SHIFT lower), the
    height a closed tab is cut off at, and the pages' content rect (left, top, right, bottom), all in the
    tab box."""
    root = everything()
    frames, anims = items(root, 'FrameTemplate'), items(root, 'Ui2DAnimation')

    def piece(template, side):
        return rect_of(anims[frames[tabs.findtext(template)].findtext(side)])[2:]

    def tab(side):
        return piece('TabBorderTemplate', side)

    def page(side):
        return piece('PageBorderTemplate', side)

    width, height = box(tabs)[2:]
    # The row starts at the box's font height + 8 (font 3's line is 14) and grows to a taller icon plus the
    # tab border's Top.
    icon_height = max(rect_of(anims[p.findtext(t)])[3] for p in pages for t in ('TabIcon', 'TabIconActive'))
    font_row = skin.TEXT_HEIGHT + 8
    assert number(tabs, 'Font') == skin.TEXT_FONT
    row = icon_height + tab('Top')[1] if icon_height > font_row else font_row
    shares = width - tab('TopLeft')[0] - tab('TopRight')[0]
    edges = [shares * i // len(pages) for i in range(len(pages) + 1)]
    spots = [(page('TopLeft')[0] + edges[i] + tab('Left')[0], tab('Top')[1]) for i in range(len(pages))]
    # Each tab's icon fits its share less the tab border's Left and Right.
    for i, p in enumerate(pages):
        assert edges[i + 1] - edges[i] - tab('Left')[0] - tab('Right')[0] >= rect_of(anims[p.findtext('TabIcon')])[2]
    area_top = row - tab('LeftBottom')[1]
    content = (page('LeftTop')[0], area_top + page('Top')[1], width - page('RightTop')[0], height - page('Bottom')[1])
    return spots, row - page('Bottom')[1], content


def test_actions_tab_and_page_borders_have_every_piece_the_client_reads():
    # The first build left most pieces out and crashed the game on load (it reads the tab border's Top without
    # checking). Every piece the stock templates have is there, clear, at least a pixel each way.
    root = everything()
    frames, anims = items(root, 'FrameTemplate'), items(root, 'Ui2DAnimation')
    atlas = decode(files()[skin.PIECES_TEXTURE])
    for name, stock in ((skin.TAB_BORDER, STOCK_TAB_BORDER), (skin.PAGE_BORDER, STOCK_PAGE_BORDER),
                        (skin.LIST_PAGE_BORDER, STOCK_PAGE_BORDER)):
        sides = [e for e in frames[name] if not e.tag.startswith('Overlap')]
        assert [e.tag for e in sides] == stock, name
        for e in sides:
            image = cut(atlas, anims[e.text])
            assert min(image.size) >= 1 and {p[3] for p in pixels(image)} == {0}, (name, e.tag)


def test_actions_tabs_are_the_pages_icons_as_toggles_lit_while_open():
    root, window, tabs, pages = actions_pages()
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(everything(), 'Ui2DAnimation')
    icons = []
    for page, width in zip((items(root, 'Page')[p.text] for p in tabs.findall('Pages')), skin.TAB_WIDTHS):
        normal, active = page.findtext('TabIcon'), page.findtext('TabIconActive')
        icon = normal.removeprefix('TUI_Tab').removesuffix('Normal')
        assert active == f'TUI_Tab{icon}Pressed' and icon in skin.ICONS
        # The tab, a toggle as wide as its share of the row, closed at the top of its art and open TAB_SHIFT
        # lower (the client draws a closed page's tab that much lower), clear around it.
        coverage = skin.icon_coverage(skin.ICONS[icon])
        for name, state, top in ((normal, 'Normal', 0), (active, 'Pressed', skin.TAB_SHIFT)):
            art = cut(atlas, anims[name])
            assert art.size == (width, skin.TAB_ART_HEIGHT)
            toggle = as_image(skin.toggle_art(coverage, state, width, skin.TOGGLE_SIZE))
            assert art.crop((0, top, width, top + skin.TOGGLE_SIZE)).tobytes() == toggle.tobytes()
            art.paste((0, 0, 0, 0), (0, top, width, top + skin.TOGGLE_SIZE))
            assert {p[3] for p in pixels(art)} == {0}
        # See-through and borderless, so the window's own panel shows behind every page.
        assert page.findtext('Style_Transparent') == 'true' and page.findtext('Style_Border') == 'false'
        icons.append(icon)
    assert icons == ['Main', 'Abilities', 'Combat', 'Socials']


def test_each_actions_tab_has_its_pages_name_as_a_tooltip():
    # The user asked for a tooltip on each tab. The tab box has none of its own, so an empty label lies over
    # each tab with the page's name, without Style_Transparent like duxaUI's click-through effect names.
    root, window, tabs, _ = actions_pages()
    pages = [items(root, 'Page')[p.text] for p in tabs.findall('Pages')]
    spots, _, _ = tab_box_layout(tabs, pages)
    labels = direct_pieces(root, window)[1:-1]  # after the tab box, before the divider under the tabs
    assert [label.tag for label in labels] == ['Label'] * len(pages)
    names = ['Main', 'General Skills', 'Combat Skills', 'Socials']
    for label, page, (x, y), width, name in zip(labels, pages, spots, skin.TAB_WIDTHS, names):
        # The tab box is at the window's inside top left, so its tabs' spots are the labels'.
        assert box(label) == (x, y + skin.TAB_SHIFT, width, skin.TOGGLE_SIZE)
        assert label.findtext('TooltipReference') == page.findtext('TooltipReference') == name
        assert label.findtext('Text') == '' and label.find('Style_Transparent') is None


def test_actions_window_follows_the_spacing_standard():
    root, window, tabs, pages = actions_pages()
    width, height = box(window)[2:]
    # As wide as the hot button window (the user's call).
    assert width == skin.HOT_WIDTH == 174 and window.findtext('Style_Titlebar') == 'false'
    # The tab box starts at the window's inside and places the tabs and pages itself. It runs TAB_OVERHANG
    # past the inside on the right, where only the last tab's padding and the page border's side are.
    inside = width - 2 * skin.BORDER
    assert box(tabs) == (0, 0, inside + skin.TAB_OVERHANG, height - 2 * skin.BORDER)
    spots, cut_at, (left, top, right, bottom) = tab_box_layout(tabs, list(items(root, 'Page').values()))
    # Every tab lands level: the open tab's art has it TAB_SHIFT down, a closed one is drawn TAB_SHIFT lower.
    toggles = [(x, y + skin.TAB_SHIFT) for x, y in spots]
    # The tabs fill the row, a padding apart and a padding from the window's sides.
    edges = [(skin.BORDER + x, skin.BORDER + x + w) for (x, _), w in zip(toggles, skin.TAB_WIDTHS)]
    assert edges[0][0] == skin.PADDING and width - edges[-1][1] == skin.PADDING
    assert [b[0] - a[1] for a, b in zip(edges, edges[1:])] == [skin.PADDING] * (len(edges) - 1)
    assert max(skin.TAB_WIDTHS) - min(skin.TAB_WIDTHS) <= 1
    # A pixel further down than the padding, since no piece can be 0 tall (see TAB_TOP).
    assert {skin.BORDER + y for _, y in toggles} == {skin.PADDING + 1}
    toggles_bottom = toggles[0][1] + skin.TOGGLE_SIZE
    assert toggles_bottom <= cut_at  # a closed tab is never cut off
    # Under the tabs, the Effects window's divider across the content row, separating the tabs from the page
    # (the user's request), a padding under the tabs, and the pages a padding under it and in from the
    # window's sides and bottom.
    divider = direct_pieces(root, window)[-1]
    dx, dy, dw, dh = box(divider)
    assert divider.tag == 'StaticAnimation' and (skin.BORDER + dx, dw, dh) == (skin.PADDING, right - left, 1)
    line = cut(decode(files()[skin.PIECES_TEXTURE]), items(everything(), 'Ui2DAnimation')[divider.findtext('Animation')])
    assert line.size == (dw, dh) and set(pixels(line)) == {skin.ROW_DIVIDER_RGBA}
    assert dy - toggles_bottom == skin.PADDING and top - (dy + dh) == skin.PADDING
    assert skin.BORDER + left == skin.PADDING == width - (skin.BORDER + right) == height - (skin.BORDER + bottom)
    assert (right - left, bottom - top) == (skin.ACTIONS_CONTENT_WIDTH, skin.ACTIONS_PAGE_HEIGHT)
    for page, controls in pages.items():
        shown = [box(c) for c in controls.values() if box(c)[2:] != (0, 0)]
        # Everything inside the page, and at least a padding apart across or down (the pairs the client
        # swaps share one spot).
        for cx, cy, cw, ch in shown:
            assert 0 <= cx and cx + cw <= right - left and 0 <= cy and cy + ch <= bottom - top, page
        for i, a in enumerate(shown):
            for b in shown[i + 1:]:
                across = max(b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]))
                down = max(b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]))
                assert a == b or max(across, down) >= skin.PADDING, (page, a, b)
    # The socials, the tallest page, fill the page to its bottom and right edges.
    socials = [box(c) for c in pages['ActionsSocialsPage'].values()]
    assert max(cy + ch for _, cy, _, ch in socials) == bottom - top
    assert max(cx + cw for cx, _, cw, _ in socials) == right - left


def test_actions_window_lines_up_with_the_hot_button_window():
    # As wide as the hot button window (the user's call), so stacked, each tab sits over one of its columns and
    # each column of buttons over a pair of them.
    columns = [skin.PADDING + c * skin.HOT_PITCH for c in range(skin.HOT_COLUMNS)]
    assert [skin.BORDER + x for x in skin.TAB_LEFTS] == columns and skin.TAB_WIDTHS == [skin.HOT_SIZE] * 4
    assert list(skin.ACTION_WIDTHS) == [2 * skin.HOT_SIZE + skin.BUTTON_GAP] * 2


def test_actions_pages_are_two_columns_of_buttons():
    # The user's design: every page's actions in two columns of buttons filling the row, like the socials, all
    # in font 2 (font 3's "Sense Heading" wouldn't fit a column). The game writes the ability and social names
    # (their text is empty); the Main and Combat pages' own names are the buttons' text.
    _, _, _, pages = actions_pages()
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(everything(), 'Ui2DAnimation')
    ordinals = ('First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth')
    height = skin.TEXT_BUTTON_HEIGHT
    step = height + skin.PADDING
    columns = ((0, 78), (78 + skin.PADDING, 78))  # the row splits evenly
    assert columns[1][0] + columns[1][1] == skin.ACTIONS_CONTENT_WIDTH

    def across(names, top=0):
        # (ScreenID, text) in spots left to right then down, as the stock skin lays out its abilities.
        return [(s, text, (columns[n % 2][0], top + n // 2 * step, columns[n % 2][1], height))
                for n, spot in enumerate(names) for s, text in spot]

    expected = {  # page: [(ScreenID, text, (x, y, width, height))]; the client shows one of a pair in one spot
        'ActionsMainPage': across([[('AMP_CampButton', 'Camp')],
                                   [('AMP_SitButton', 'Sit'), ('AMP_StandButton', 'Stand')],
                                   [('AMP_RunButton', 'Run'), ('AMP_WalkButton', 'Walk')],
                                   [('AMP_InviteButton', 'Invite'), ('AMP_FollowButton', 'Follow')]]),
        'ActionsAbilitiesPage': across([[(f'AAP_{n}AbilityButton', '')] for n in ordinals]),
        'ActionsCombatPage': across([[('ACP_MeleeAttackButton', 'Melee Attack')],
                                     [('ACP_RangeAttackButton', 'Range Attack')]]
                                    + [[(f'ACP_{n}AbilityButton', '')] for n in ordinals[:4]]),
        # Under the page arrows, the game's columns of six, 1 to 6 then 7 to 12, with the bottom three rows (4,
        # 5, 6, 10, 11 and 12) hidden.
        'ActionsSocialsPage': [(f'ASP_SocialButton{n + 1}', '',
                                (columns[n // 6][0], skin.ARROW_SIZE + skin.PADDING + n % 6 * step, columns[n // 6][1],
                                 height)) for n in range(12) if n % 6 < 3],
    }
    for page, spots in expected.items():
        buttons = [b for b in pages[page].values() if b.tag == 'Button' and b.find('Font') is not None]
        assert [(b.findtext('ScreenID'), b.findtext('Text'), box(b)) for b in buttons] == spots, page
        for b in buttons:
            assert number(b, 'Font') == 2 and rgb(b, 'TextColor') == skin.TEXT_RGB
            assert b.findtext('Style_Checkbox') == 'false' and b.find('TooltipReference') is None
            # The wash with no label of ours, as big as the button.
            for state in b.find('ButtonDrawTemplate'):
                look = skin.button_look(skin.BUTTON_STYLE, skin.BUTTON_ART[state.tag])
                plain = skin.snapped_art(skin.panel_texture(*box(b)[2:], *look))
                assert cut(atlas, anims[state.text]).tobytes() == as_image(plain).tobytes(), (b.get('item'), state.tag)
    # The socials, the tallest page, have four rows with the arrows (a row fewer than before, the user's call),
    # and the window is no taller: its outer edge a padding under the page.
    assert skin.ACTIONS_PAGE_HEIGHT == 4 * step - skin.PADDING
    assert skin.ACTIONS_HEIGHT == skin.BORDER + skin.PAGE_TOP + skin.ACTIONS_PAGE_HEIGHT + skin.PADDING == 150


def test_social_page_arrows_are_small_icon_buttons_around_the_page_number():
    _, _, _, pages = actions_pages()
    socials = pages['ActionsSocialsPage']
    left, right = socials['ASP_SocialPageLeftButton'], socials['ASP_SocialPageRightButton']
    size = (skin.ARROW_SIZE, skin.ARROW_SIZE)
    assert box(left) == (0, 0, *size) and box(right) == (skin.ACTIONS_CONTENT_WIDTH - skin.ARROW_SIZE, 0, *size)
    assert left.findtext('ButtonDrawTemplate/Normal') == 'TUI_ToggleLeftNormal'
    assert right.findtext('ButtonDrawTemplate/Normal') == 'TUI_ToggleRightNormal'
    number_label = socials['ASP_CurrentSocialPageLabel']
    x, y, w, h = box(number_label)
    # Centered between the arrows, a padding from each, its digits' ink centered on them.
    assert x == skin.ARROW_SIZE + skin.PADDING and x + w == box(right)[0] - skin.PADDING
    assert number_label.findtext('AlignCenter') == 'true' and number(number_label, 'Font') == skin.TEXT_FONT
    assert y + skin.DIGITS_INK_MIDDLE == skin.ARROW_SIZE / 2 and h == skin.TEXT_HEIGHT


def test_every_icon_is_distinct_stays_in_its_square_and_dims_when_disabled():
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(everything(), 'Ui2DAnimation')
    normals = set()
    # (icon, button width, button height): the spell bar's book button runs across the window.
    buttons = ([(n, skin.TOGGLE_SIZE, skin.TOGGLE_SIZE) for n in skin.ICONS]
               + [(n, skin.ARROW_SIZE, skin.ARROW_SIZE) for n in {**skin.ARROW_ICONS, **skin.SIGN_ICONS}]
               + [('Book', skin.BOOK_WIDTH, skin.TOGGLE_SIZE)])
    for name, width, height in buttons:
        left, top = (width - skin.ICON_SIZE) // 2, (height - skin.ICON_SIZE) // 2
        icon_box = (left, top, left + skin.ICON_SIZE, top + skin.ICON_SIZE)
        for state, (fill, edge, _) in skin.ICON_LOOKS.items():
            art = cut(atlas, anims[f'TUI_Toggle{name}{state}'])
            assert art.size == (width, height), name
            # Outside the centered 16px square, the art is the plain button.
            plain = as_image(skin.snapped_art(skin.panel_texture(width, height, fill, edge)))
            art.paste((0, 0, 0, 0), icon_box)
            plain.paste((0, 0, 0, 0), icon_box)
            assert art.tobytes() == plain.tobytes(), (name, state)
        art = {state: cut(atlas, anims[f'TUI_Toggle{name}{state}']).crop(icon_box) for state in skin.ICON_LOOKS}
        ink = {state: max(sum(p[:3]) * p[3] for p in pixels(image)) for state, image in art.items()}
        assert ink['Disabled'] < ink['Normal'] < ink['Flyby'], name
        normals.add(art['Normal'].tobytes())
    assert len(normals) == len(buttons)


@pytest.mark.parametrize('name, item, slots, first_type', [
    (skin.BUFF_FILE, 'BuffWindow', 15, 45), (skin.SONG_FILE, 'ShortDurationBuffWindow', 6, 135)])
def test_effects_are_a_table_of_rows_icon_then_name(name, item, slots, first_type):
    # EQ Triage's table look, as the user asked: a row per slot, compact, with a divider between. Wider than
    # the other windows' 200, so longer names fit after the icon and its harmful bars (the user's calls).
    assert skin.EFFECTS_WIDTH == 232
    root, window = check_inside_frame(name, skin.EFFECTS_WIDTH)
    assert window.get('item') == item
    every_button = list(root.iter('Button'))
    assert [b.findtext('ScreenID') for b in every_button] == [f'Buff{n}' for n in range(skin.CLIENT_SLOTS)]
    # The client looks up Buff0 to Buff14 in both windows (UIErrors.txt reported the songs window's missing
    # ones), so the slots a window doesn't show are hidden: no size, clear art.
    buttons, hidden = every_button[:slots], every_button[slots:]
    assert skin.CLIENT_SLOTS == 15
    for b in hidden:
        assert box(b)[2:] == (0, 0)
        assert {b.findtext(f'ButtonDrawTemplate/{state}') for state in skin.BUTTON_STATES} == {'TUI_Clear'}
    names = {e.findtext('ScreenID'): e for e in root.iter('Label')}
    inside = box(window)[2] - 2 * skin.BORDER
    for n, b in enumerate(buttons):
        x, y, w, h = box(b)
        # Across the row but inset, so it's narrower than the window's inside: the client lays the slots out
        # itself, a pixel apart, and never hit-tested slots as wide as the inside (no tooltip, no click, no
        # red for harmful effects in game). Two don't fit across, so one per row, where eqgame.exe puts it
        # (0x4090E9): the inside's width less the slot's and a pixel, a pixel right of the dividers.
        assert (x, y, w, h) == (skin.SLOT_X, n * skin.ROW_PITCH, skin.SLOT_WIDTH, skin.ROW_HEIGHT)
        assert skin.SLOT_WIDTH == inside - 2 * skin.LEFT == 220 and 2 * (w + 1) > inside
        assert skin.SLOT_X == inside - (skin.SLOT_WIDTH + 1) == skin.LEFT + 1
        assert skin.ROW_PITCH == skin.ROW_HEIGHT + 1
        # The client paints the background and the spell's icon. Zeal's time left sits at the button's
        # top left (it covered the names' first letters in game), so the icon comes a padding after a
        # column for it, a padding from the window's top and bottom.
        assert b.findtext('ButtonDrawTemplate/Normal') == 'BlueIconBackground'
        assert b.findtext('ButtonDrawTemplate/NormalDecal') == skin.BUFF_ICONS
        # The decal offset is within the slot; the icon's place in the window stays ROW_ICON_X.
        assert (x + number(b, 'DecalOffset/X'), number(b, 'DecalOffset/Y')) == (skin.ROW_ICON_X, skin.ROW_ICON_MARGIN)
        # A column for Zeal's time box from the slot's left (the user's calls: at 18 and then 23 the box
        # covered some icons; 30 keeps 2px from the harmful bar), then the icon a bar's width in, 41px from
        # the window's edge.
        assert number(b, 'DecalOffset/X') == skin.TIMER_WIDTH + skin.HARMFUL_BAR_WIDTH == 34
        assert skin.TIMER_WIDTH == 30
        assert skin.BORDER + skin.ROW_ICON_X == skin.PADDING + 1 + skin.TIMER_WIDTH + skin.HARMFUL_BAR_WIDTH == 41
        assert (number(b, 'DecalSize/CX'), number(b, 'DecalSize/CY')) == (skin.ROW_ICON, skin.ROW_ICON)
        assert skin.BORDER + skin.ROW_ICON_MARGIN == skin.PADDING
        # The name a padding after the right harmful bar's place, which touches the icon (the user's
        # design), centered in the row, ending a padding from the edge.
        label = names[f'Buff{n}Label']
        lx, ly, lw, lh = box(label)
        assert label.findtext('EQType') == str(first_type + n) and not label.findtext('Text')
        assert lx == skin.ROW_NAME_X == skin.ROW_ICON_X + skin.ROW_ICON + skin.HARMFUL_BAR_WIDTH + skin.PADDING
        assert lx + lw == skin.EFFECTS_RIGHT
        assert skin.BORDER + skin.EFFECTS_RIGHT == skin.EFFECTS_WIDTH - skin.PADDING and lw == 159
        assert ly - y == (skin.ROW_HEIGHT - lh) // 2
    # A divider in each pixel between rows, as long as the slots, softer than the bars' track (the user).
    dividers = [box(e) for e in root.iter('StaticAnimation')]
    assert dividers == [(skin.LEFT, n * skin.ROW_PITCH - 1, skin.SLOT_WIDTH, 1) for n in range(1, slots)]
    assert {e.findtext('Animation') for e in root.iter('StaticAnimation')} == {'TUI_RowDivider'}
    line = cut(decode(files()[skin.PIECES_TEXTURE]), items(everything(), 'Ui2DAnimation')['TUI_RowDivider'])
    assert set(pixels(line)) == {skin.ROW_DIVIDER_RGBA} and skin.ROW_DIVIDER_RGBA[3] < skin.EDGE_FADED[3]
    assert line.size == (skin.SLOT_WIDTH, 1)
    assert box(window)[3] == 2 * skin.BORDER + slots * skin.ROW_PITCH - 1
    # The rows are solid, so the names are drawn after the buttons, over them, as in duxaUI (where a click
    # on a name clicks the effect off); the hidden slots come last.
    order = [p.text for p in window.findall('Pieces')]
    first_name = min(order.index(e.get('item')) for e in root.iter('Label'))
    assert all(order.index(b.get('item')) < first_name for b in buttons)
    shown = len(order) - len(hidden)
    assert order[shown - slots:shown] == [names[f'Buff{n}Label'].get('item') for n in range(slots)]
    assert order[shown:] == [b.get('item') for b in hidden]


def test_spell_bar_is_a_table_of_gems_with_names_recast_bars_and_the_book():
    # duxaUI's gems (the user's pick) in the Effects window's table look: a row per gem, its icon and then the
    # spell's name, Zeal's recast countdown under the name, the global recovery on top and the book under.
    # 190 wide (the user's call), with the usual padding each side.
    assert skin.SPELL_BAR_WIDTH == 190
    root, window = check_inside_frame(skin.CASTSPELL_FILE, skin.SPELL_BAR_WIDTH)
    assert window.get('item') == 'CastSpellWnd'
    inner_width, height = box(window)[2] - 2 * skin.BORDER, box(window)[3]
    right = inner_width - skin.LEFT  # a padding from the window's right edge
    assert right == skin.SPELL_BAR_RIGHT
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(everything(), 'Ui2DAnimation')
    # The client looks up the eight gems and the book's button.
    gems = list(root.iter('SpellGem'))
    assert [g.findtext('ScreenID') for g in gems] == [f'CSPW_Spell{n}' for n in range(8)]
    assert [b.findtext('ScreenID') for b in root.iter('Button')] == ['CSPW_SpellBook']
    names = {e.findtext('ScreenID'): e for e in root.iter('Label')}
    gauges = {e.findtext('ScreenID'): e for e in root.iter('Gauge')}
    for n, gem in enumerate(gems):
        x, y, w, h = box(gem)
        # As wide as the window's inside, so a click anywhere on the row casts; a pixel between rows.
        assert (x, y, w, h) == (0, skin.GEMS_TOP + n * skin.GEM_ROW_PITCH, inner_width, skin.GEM_ROW_HEIGHT)
        assert skin.GEM_ROW_PITCH == skin.GEM_ROW_HEIGHT + 1
        # The client's 24px icon a padding from the window's left edge, centered in a 32px row, roomier than the
        # Effects table's so the rows are big targets (the user's calls: 36 was a bit too large).
        assert (number(gem, 'SpellIconOffsetX'), number(gem, 'SpellIconOffsetY')) == (skin.LEFT, skin.GEM_ICON_MARGIN)
        assert skin.BORDER + skin.LEFT == skin.PADDING and h == skin.GEM_ICON + 2 * skin.GEM_ICON_MARGIN == 32
        # Under the icon, a clear row exactly the gem's size, empty or not: solid rows in the panel's color
        # showed as a background under each row at the window's Alpha of 230, and the user had them removed.
        template = gem.find('SpellGemDrawTemplate')
        for part in ('Holder', 'Background'):
            art = cut(atlas, anims[template.findtext(part)])
            assert art.size == (w, h) and {p[3] for p in pixels(art)} == {0}, part
        assert template.findtext('Highlight') == 'TUI_Clear'
        # The name a padding after the icon, centered in the row, ending a padding from the edge.
        name = names[f'CSPW_Spell{n}_Name']
        nx, ny, nw, nh = box(name)
        assert name.findtext('EQType') == str(60 + n) and not name.findtext('Text')
        assert nx == skin.LEFT + skin.GEM_ICON + skin.PADDING and nx + nw == right
        assert ny - y == (h - nh) // 2
        # Zeal's recast countdown for the gem, its text hidden: a thin bar a pixel under the name's line and as
        # long, inside the row.
        recast = gauges[f'CSPW_Spell{n}_Recast']
        assert recast.findtext('EQType') == str(26 + n) and number(recast, 'TextOffsetY') == 8000
        assert box(recast) == (nx, ny + nh + skin.PET_BAR_GAP, nw, skin.TICK_HEIGHT)
        assert ny + nh + skin.PET_BAR_GAP + skin.TICK_HEIGHT <= y + h
    # Zeal's global recovery along the top, the first icon a padding under it.
    recovery = gauges['CSPW_Global_Recast']
    assert recovery.findtext('EQType') == '25' and number(recovery, 'TextOffsetY') == 8000
    assert box(recovery) == (skin.LEFT, 0, right - skin.LEFT, skin.TICK_HEIGHT)
    assert box(gems[0])[1] + skin.GEM_ICON_MARGIN - skin.TICK_HEIGHT == skin.PADDING
    # Regular bars with no tracks (see the bar test for their fills): the gems' plain white like the other
    # windows' bars, not subdued (the user's request), and the global recovery, the master timer, in the casting
    # window's soft red (the user's idea).
    for bar in [recovery] + [gauges[f'CSPW_Spell{n}_Recast'] for n in range(8)]:
        assert bar.find('GaugeDrawTemplate/Background') is None
    assert rgb(recovery, 'FillTint') == skin.SPELL_RGB
    assert {rgb(gauges[f'CSPW_Spell{n}_Recast'], 'FillTint') for n in range(8)} == {skin.TEXT_RGB}
    # A divider in the pixel under each row, as in the Effects window, the last gem's too (the user's request).
    assert [box(e) for e in root.iter('StaticAnimation')] == [
        (skin.LEFT, skin.GEMS_TOP + n * skin.GEM_ROW_PITCH - 1, right - skin.LEFT, 1) for n in range(1, 9)]
    assert {e.findtext('Animation') for e in root.iter('StaticAnimation')} == {'TUI_SpellBarDivider'}
    line = cut(atlas, anims['TUI_SpellBarDivider'])
    assert line.size == (right - skin.LEFT, 1) and set(pixels(line)) == {skin.ROW_DIVIDER_RGBA}
    # The book: an icon toggle like the selector's but across the window, a big target for a hurried click (the
    # user's request), pressed while the book is open, with the default tooltip. In a row of its own under the
    # last gem's divider, for balance: a padding under it and from the window's sides. Under it, as many clear
    # pixels as over it: the window's 1px edge line doesn't count toward the gap (the user saw the gap under
    # the book smaller than the one over it when it did).
    book = next(root.iter('Button'))
    bx, by, bw, bh = box(book)
    assert (bx, bw, bh) == (skin.LEFT, right - skin.LEFT, skin.TOGGLE_SIZE)
    assert skin.BORDER + bx == skin.PADDING == box(window)[2] - (skin.BORDER + bx + bw)
    last_divider = box(list(root.iter('StaticAnimation'))[-1])
    assert last_divider[1] == box(gems[-1])[1] + skin.GEM_ROW_HEIGHT
    clear_over = by - (last_divider[1] + 1)
    edge_line = height - skin.EDGE_LINE  # the window's last row
    assert clear_over == edge_line - (skin.BORDER + by + bh) == skin.PADDING
    column = [row[box(window)[2] // 2] for row in skin.panel_texture(box(window)[2], height).rows]
    assert column[edge_line] != skin.PANEL_RGBA and column[edge_line - 1] == skin.PANEL_RGBA
    assert book.findtext('Style_Checkbox') == 'true'
    assert book.findtext('TooltipReference') == 'Opens and closes Your Spellbook'
    assert {s.text for s in book.find('ButtonDrawTemplate')} == {
        f'TUI_ToggleBook{skin.TOGGLE_ART[state]}' for state in skin.BUTTON_STATES}
    # The names and bars are drawn over the gems.
    order = [p.text for p in window.findall('Pieces')]
    assert max(order.index(g.get('item')) for g in gems) < min(order.index(e.get('item')) for e in names.values())


def hot_bar():
    """The hot button window's file, the window, and its controls by ScreenID."""
    root, window = check_inside_frame(skin.HOTBUTTON_FILE, skin.HOT_WIDTH)
    return root, window, {e.findtext('ScreenID'): e for e in root if e.findtext('ScreenID')}


def test_hot_button_window_keeps_every_control_the_client_looks_for():
    # The stock window's controls, which every skin keeps: the page arrows and number, and on each of the ten
    # macros' spots a button, an item slot (EQType -1) and a spell gem, the three the same size.
    root, window, controls = hot_bar()
    assert window.get('item') == 'HotButtonWnd'
    assert {'HB_PageLeftButton', 'HB_PageRightButton', 'HB_CurrentPageLabel'} <= set(controls)
    for n in range(1, 11):
        button, item, gem = (controls[f'HB_{kind}{n}'] for kind in ('Button', 'InvSlot', 'SpellGem'))
        assert (button.tag, item.tag, gem.tag) == ('Button', 'InvSlot', 'SpellGem')
        assert item.findtext('EQType') == '-1'
        assert box(button) == box(item) == box(gem)
    # Nothing is hidden, and in duxaUI's order: the page row, the buttons, the item slots and gems over them, then
    # the weapon and bag slots.
    order = [p.text for p in window.findall('Pieces')]
    kinds = [items(root, tag) for tag in ('Button', 'Label', 'InvSlot', 'SpellGem')]
    assert all(box(e)[2:] != (0, 0) for e in direct_pieces(root, window))
    assert order[:3] == [controls[i].get('item') for i in ('HB_PageLeftButton', 'HB_PageRightButton',
                                                            'HB_CurrentPageLabel')]
    assert order[3:] == ([controls[f'HB_{kind}{n}'].get('item') for kind in ('Button', 'InvSlot', 'SpellGem')
                          for n in range(1, 11)]
                         + [e.get('item') for e in root.iter('InvSlot') if e.findtext('EQType') != '-1'])
    assert len(order) == sum(len(k) for k in kinds) == 3 + 30 + 12


def test_hot_button_window_is_duxaUIs_shape_on_a_grid_of_36px_spots():
    # The user's picks: duxaUI's shape, everything 36px and a padding apart (4px was tried in game; the user went
    # back to the standard), so the rows line up across the window. Four columns of six rows: the page row and the
    # ten macros on the left, the weapon slots and the bags on the right.
    root, window, controls = hot_bar()
    assert box(window)[2:] == (skin.HOT_WIDTH, skin.HOT_HEIGHT) == (174, 258)
    step = skin.HOT_SIZE + skin.PADDING

    def spot(column, row):
        return skin.LEFT + column * step, skin.LEFT + row * step

    # A padding from the window's edges on every side.
    width, height = box(window)[2:]
    assert skin.BORDER + spot(0, 0)[0] == skin.PADDING
    assert width - (skin.BORDER + spot(3, 5)[0] + skin.HOT_SIZE) == skin.PADDING
    assert height - (skin.BORDER + spot(3, 5)[1] + skin.HOT_SIZE) == skin.PADDING
    # The macros under the page row, left to right then down, as in duxaUI.
    for n in range(1, 11):
        assert box(controls[f'HB_Button{n}']) == (*spot((n - 1) % 2, 1 + (n - 1) // 2), 36, 36)
    # Beside them, Primary and Secondary, Range and Ammo, then the bags down each column, 1 to 4 and 5 to 8.
    slots = [e for e in root.iter('InvSlot') if e.findtext('EQType') != '-1']
    assert {box(e)[2:] for e in slots} == {(36, 36)}
    placed = {box(e)[:2]: int(e.findtext('EQType')) for e in slots}
    assert [[placed[spot(c, r)] for r in range(6)] for c in (2, 3)] == [[13, 11, 22, 23, 24, 25],
                                                                        [14, 21, 26, 27, 28, 29]]
    # With duxaUI's ScreenIDs for the same slots, and its style flags: right-clicks on items there stopped
    # working in game with ScreenIDs of our own.
    duxa = {'NewSlot1': 13, 'Newslot2': 11, 'Newslot3': 22, 'Newslot4': 23, 'Newslot5': 24, 'Newslot6': 25,
            'Newslot7': 14, 'Newslot8': 21, 'Newslot9': 26, 'Newslot10': 27, 'Newslot11': 28, 'Newslot12': 29}
    assert {e.findtext('ScreenID'): int(e.findtext('EQType')) for e in slots} == duxa
    for e in root.iter('InvSlot'):
        assert [e.findtext(f) for f in ('Style_VScroll', 'Style_HScroll', 'Style_Transparent')] == ['false'] * 3


def test_hot_button_page_arrows_are_a_row_tall_around_the_page_number():
    # The page row is as tall as the others so the rows line up: the Actions window's chevrons, as wide as its
    # arrows, at the two ends of the macro columns, and the page number between them, its digits centered.
    root, window, controls = hot_bar()
    left, right, page = (controls[i] for i in ('HB_PageLeftButton', 'HB_PageRightButton', 'HB_CurrentPageLabel'))
    macros = box(controls['HB_Button1']), box(controls['HB_Button2'])
    assert box(left) == (macros[0][0], skin.LEFT, skin.ARROW_SIZE, skin.HOT_SIZE)
    assert box(right) == (macros[1][0] + skin.HOT_SIZE - skin.ARROW_SIZE, skin.LEFT, skin.ARROW_SIZE, skin.HOT_SIZE)
    x, y, w, h = box(page)
    assert x == box(left)[0] + skin.ARROW_SIZE + skin.PADDING and x + w == box(right)[0] - skin.PADDING
    assert page.findtext('AlignCenter') == 'true' and number(page, 'Font') == skin.TEXT_FONT
    assert y + skin.DIGITS_INK_MIDDLE == skin.LEFT + skin.HOT_SIZE / 2 and h == skin.TEXT_HEIGHT
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(everything(), 'Ui2DAnimation')
    tip_row = skin.HOT_SIZE // 2 - 1
    art = {}
    for arrow, way, tooltip in ((left, 'Left', 'Previous Page'), (right, 'Right', 'Next Page')):
        assert arrow.findtext('TooltipReference') == tooltip and arrow.findtext('Style_Checkbox') == 'false'
        assert {s.tag: s.text for s in arrow.find('ButtonDrawTemplate')} == {
            state: f'TUI_ToggleHot{way}{skin.ICON_ART[state]}' for state in skin.BUTTON_STATES}
        art[way] = {state: cut(atlas, anims[f'TUI_ToggleHot{way}{state}']) for state in skin.ICON_LOOKS}
        assert {a.size for a in art[way].values()} == {(skin.ARROW_SIZE, skin.HOT_SIZE)}
        # Lit when hovered, dimmed when disabled, like the other icon buttons.
        ink = {state: max(sum(p[:3]) for p in pixels(a)) for state, a in art[way].items()}
        assert ink['Disabled'] < ink['Normal'] < ink['Flyby'], way
    # Each points its way: its tip, halfway down, is on its own side.
    def light(way, x):
        return sum(art[way]['Normal'].getpixel((x, tip_row))[:3])
    assert light('Left', 8) > light('Right', 8) and light('Right', 11) > light('Left', 11)


def test_macro_names_are_the_games_text_in_font_1():
    # The game writes each macro's name, in font 1, the small font duxaUI uses (the user's pick).
    root, window, controls = hot_bar()
    for n in range(1, 11):
        button = controls[f'HB_Button{n}']
        assert number(button, 'Font') == skin.MACRO_FONT == 1
        assert not button.findtext('Text') and rgb(button, 'TextColor') == skin.TEXT_RGB
        assert button.findtext('Style_Checkbox') == 'false'
        assert {s.tag: s.text for s in button.find('ButtonDrawTemplate')} == {
            state: f'TUI_HotButton{skin.BUTTON_ART[state]}' for state in skin.BUTTON_STATES}
        assert (number(button, 'DecalSize/CX'), number(button, 'DecalSize/CY')) == (skin.HOT_SIZE, skin.HOT_SIZE)


def test_hot_button_window_art_is_solid_and_empty_slots_show_dimmed_icons():
    root, window, controls = hot_bar()
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(everything(), 'Ui2DAnimation')
    # Solid everywhere, rounded corners too, so every click lands (see HELPFUL_RGBA): the buttons' look over the
    # panel, which shows in the corners.
    used = {e.text for tag in ('ButtonDrawTemplate', 'SpellGemDrawTemplate') for t in root.iter(tag) for e in t}
    used |= {e.findtext('Background') for e in root.iter('InvSlot')}
    for name in used - {'TUI_Clear'}:
        art = cut(atlas, anims[name])
        assert {p[3] for p in pixels(art)} == {255}, name
        assert art.getpixel((0, 0)) == skin.PANEL_RGBA, name
    fill_spot = (skin.HOT_SIZE // 2, 2)  # clear of the edge and of an icon
    for state in skin.BUTTON_LOOKS:
        fill = skin.button_look('Wash', state)[0]
        assert cut(atlas, anims[f'TUI_HotButton{state}']).getpixel(fill_spot) == skin.snapped(
            skin.over(fill, 1, skin.PANEL_RGBA))
    # Each empty weapon slot shows its own icon, big, in the middle of the macros' plain button (see the next
    # test), in the row dividers' color as it shows over the panel (the user wanted them subdued). An empty bag
    # slot is the plain button: anything goes there, and a sack icon read as a ring in game (the user).
    slots = [e for e in root.iter('InvSlot') if e.findtext('EQType') != '-1']
    icons = {int(e.findtext('EQType')): e.findtext('Background') for e in slots}
    assert [icons[t] for t in (13, 14, 11, 21)] == [f'TUI_HotSlot{n}' for n in ('Primary', 'Secondary', 'Range', 'Ammo')]
    assert {icons[t] for t in range(22, 30)} == {'TUI_HotButtonNormal'}
    inset = int((skin.HOT_SIZE - skin.SLOT_ICON_SHARE * skin.HOT_SIZE) / 2)  # 4: the ink starts 4.5px in
    icon_box = (inset, inset, skin.HOT_SIZE - inset, skin.HOT_SIZE - inset)
    divider = skin.snapped(skin.over(skin.ROW_DIVIDER_RGBA, 1, skin.PANEL_RGBA))
    plain = cut(atlas, anims['TUI_HotButtonNormal'])
    plain.paste((0, 0, 0, 0), icon_box)
    drawn = set()
    for name in skin.SLOT_ICONS:
        art = cut(atlas, anims[f'TUI_HotSlot{name}'])
        assert art.size == (skin.HOT_SIZE, skin.HOT_SIZE)
        drawn.add(art.crop(icon_box).tobytes())
        assert max(pixels(art.crop(icon_box)), key=lambda p: sum(p[:3])) == divider, name
        assert sum(divider[:3]) > sum(plain.getpixel(fill_spot)[:3])
        art.paste((0, 0, 0, 0), icon_box)
        assert art.tobytes() == plain.tobytes(), name
    # The four weapons', and the inventory window's other worn slots' (see its tests), each its own.
    assert len(drawn) == len(skin.SLOT_ICONS) == 18


def test_the_empty_slots_icons_fill_three_quarters_of_the_slot():
    # The user asked for the sword, shield, bow and arrow to take about 75% of the slot's diagonal: each icon's
    # ink fills a box 75% of the slot's side at its longer side (27px, 4.5px in from each side), centered on the
    # slot, so the sword and arrow, running corner to corner, take about 75% of the diagonal.
    for name, shape in skin.SLOT_ICONS.items():
        coverage = skin.slot_icon_coverage(shape)
        assert len(coverage) == len(coverage[0]) == skin.HOT_SIZE
        rows = [y for y, row in enumerate(coverage) if max(row)]
        columns = [x for x in range(skin.HOT_SIZE) if max(row[x] for row in coverage)]
        assert max(rows[-1] - rows[0], columns[-1] - columns[0]) == 27, name  # ink from 4.5 to 31.5: pixels 4 to 31
        assert rows[0] + rows[-1] == columns[0] + columns[-1] == skin.HOT_SIZE - 1, name  # centered
        if name in ('Primary', 'Ammo'):
            # Along the diagonal: a pixel's x - y steps by 2 for every pixel diagonal (HOT_SIZE of them).
            inked = [(x, y) for y, row in enumerate(coverage) for x, amount in enumerate(row) if amount]
            along = max(x - y for x, y in inked) - min(x - y for x, y in inked)
            assert 0.7 < along / (2 * skin.HOT_SIZE) < 0.8, name


def test_hot_button_spell_gems_center_the_spells_icon_on_the_button():
    # The client draws a gem's Holder and Background under the spell's 24px icon (see the spell bar), so both
    # are the macros' plain button and the icon sits in its middle.
    root, window, controls = hot_bar()
    for n in range(1, 11):
        gem = controls[f'HB_SpellGem{n}']
        offsets = number(gem, 'SpellIconOffsetX'), number(gem, 'SpellIconOffsetY')
        assert offsets == (skin.HOT_GEM_OFFSET,) * 2 and 2 * skin.HOT_GEM_OFFSET + skin.GEM_ICON == skin.HOT_SIZE
        template = gem.find('SpellGemDrawTemplate')
        assert [template.findtext(p) for p in ('Holder', 'Background', 'Highlight')] == [
            'TUI_HotButtonNormal', 'TUI_HotButtonNormal', 'TUI_Clear']


BAG_IDS = ['Container_Label', 'Container_Icon', *(f'ContainerSlot{n}' for n in range(1, 11)), 'Container_Combine',
           'DoneButton']


def bag_window():
    """The bag window's file, the window, and its controls by ScreenID."""
    root, window = check_inside_frame(skin.CONTAINER_FILE, skin.BAG_WIDTH)
    return root, window, {e.findtext('ScreenID'): e for e in direct_pieces(root, window)}


def bag_layout(slots, tradeskill):
    """The bag window as the client lays it out for a bag of that many slots (eqgame.exe, SetContainer at
    0x41717D): a box around the label, the icon and the visible slots, each measured as a plain rectangle, a
    control of no size as a point; Combine (in a tradeskill container) then Done moved BAG_BUTTON_GAP under it,
    each growing it by its XML height; the window the box plus 14 across and 36 down. Returns the window's outer
    size and where the visible controls are drawn, by ScreenID: the slots where they are, the anchored buttons
    where their anchors put them in the window's inside."""
    root, window = screen(skin.CONTAINER_FILE)
    controls = {e.findtext('ScreenID'): e for e in direct_pieces(root, window)}
    shown = [f'ContainerSlot{n}' for n in range(1, slots + 1)]
    edges = []
    for screen_id in ['Container_Label', 'Container_Icon', *shown]:
        x, y, w, h = box(controls[screen_id])
        edges.append((x, y, x + w, y + h))
    left, top = min(e[0] for e in edges), min(e[1] for e in edges)
    right, bottom = max(e[2] for e in edges), max(e[3] for e in edges)
    for screen_id in (['Container_Combine'] if tradeskill else []) + ['DoneButton']:
        bottom += skin.BAG_BUTTON_GAP + box(controls[screen_id])[3]
        shown.append(screen_id)
    width, height = right - left + skin.BAG_EXTRA_WIDTH, bottom - top + skin.BAG_EXTRA_HEIGHT
    inside = width - 2 * skin.BORDER, height - 2 * skin.BORDER
    drawn = {screen_id: anchored_rect(controls[screen_id], inside)
             if controls[screen_id].findtext('AutoStretch') == 'true' else box(controls[screen_id])
             for screen_id in shown}
    return (width, height), drawn


def test_bag_window_keeps_every_control_the_client_looks_for():
    # eqgame.exe looks up the label, the icon, ContainerSlot1 to 10, Combine and DoneButton by ScreenID (the
    # constructor at 0x416AE1) and no more: the installed copy of duxaUI's, which has no icon, logged "Could not find
    # child Container_Icon". Each once, in the stock order.
    root, window, controls = bag_window()
    assert window.get('item') == 'ContainerWindow'
    assert [e.findtext('ScreenID') for e in direct_pieces(root, window)] == BAG_IDS
    slots = [controls[f'ContainerSlot{n}'] for n in range(1, 11)]
    assert {s.tag for s in slots} == {'InvSlot'} and [int(s.findtext('EQType')) for s in slots] == list(range(30, 40))
    # duxaUI's flags, and the hot bar's plain slot, solid like everything there (see its tests).
    for s in slots:
        assert [s.findtext(f) for f in ('Style_VScroll', 'Style_HScroll', 'Style_Transparent')] == ['false'] * 3
        assert s.findtext('Background') == 'TUI_HotButtonNormal'
    assert [controls[i].tag for i in ('Container_Icon', 'Container_Combine', 'DoneButton')] == ['Button'] * 3
    # A fixed size like the other windows, so it drags by its background, and no title bar or close box: Done, Esc
    # or the bag's own slot close it.
    assert window.findtext('Style_Sizable') == 'false' and window.findtext('Style_Closebox') == 'false'


def test_bags_show_no_name_or_icon_but_keep_both_at_the_grids_top_corners():
    # The bags don't need to show their own name (the user). The client writes it into the label and puts the bag's
    # icon on the icon button, so both stay, with no size or text. Its box starts with them, so they sit at the
    # grid's top corners, points that make every bag's window the grid's width from the grid's top: at 0, 0 the
    # window would have 4px on the left and 10 on the right, and a bag of a few slots a narrower window.
    root, window, controls = bag_window()
    label, icon = controls['Container_Label'], controls['Container_Icon']
    assert label.tag == 'Label' and not label.findtext('Text') and label.find('EQType') is None
    assert {s.text for s in icon.find('ButtonDrawTemplate')} == {'TUI_Clear'} and not icon.findtext('Text')
    first, last = box(controls['ContainerSlot1']), box(controls[f'ContainerSlot{skin.BAG_COLUMNS}'])
    assert box(icon) == (*first[:2], 0, 0) == (skin.BAG_LEFT, skin.BAG_TOP, 0, 0)
    assert box(label) == (last[0] + last[2], last[1], 0, 0)
    assert {bag_layout(slots, False)[0][0] for slots in range(1, 11)} == {skin.BAG_WIDTH}


def test_bag_window_follows_the_spacing_standard_for_every_bag():
    # The user's picks: the hot bar's 36px spots two across, as in duxaUI (four across didn't suit the user in
    # game), the window hugging each bag, Done across the bottom and Combine over it in a tradeskill container. The
    # game adds 14px across, so the sides are 7px each (the user's pick over 6 and 8); down, everything is the
    # standard's.
    assert (skin.BAG_EXTRA_WIDTH, skin.BAG_EXTRA_HEIGHT, skin.BAG_BUTTON_GAP) == (14, 36, 4)  # eqgame.exe's
    step = skin.HOT_SIZE + skin.PADDING
    heights = {}
    for slots in range(1, 11):
        for tradeskill in (False, True):
            (width, height), drawn = bag_layout(slots, tradeskill)
            heights[slots, tradeskill] = height
            inside = width - 2 * skin.BORDER, height - 2 * skin.BORDER
            for screen_id, (x, y, w, h) in drawn.items():
                assert 0 <= x and x + w <= inside[0] and 0 <= y and y + h <= inside[1], (slots, screen_id)
            # The slots 36px, a padding apart, two to a row, 7px from the sides and 6 from the top.
            grid = [drawn[f'ContainerSlot{n}'] for n in range(1, slots + 1)]
            for n, spot in enumerate(grid):
                assert spot == (skin.BAG_LEFT + n % 2 * step, skin.BAG_TOP + n // 2 * step, 36, 36)
            assert width == skin.BAG_WIDTH == 92
            assert skin.BORDER + skin.BAG_LEFT == 7 == width - (skin.BORDER + skin.BAG_LEFT + skin.BAG_CONTENT_WIDTH)
            assert skin.BORDER + skin.BAG_TOP == skin.PADDING
            # Then the buttons across the grid, a padding under the last row and apart, and the window's edge a
            # padding under Done.
            buttons = [drawn[i] for i in ('Container_Combine', 'DoneButton') if i in drawn]
            assert len(buttons) == 1 + tradeskill
            above = grid[-1][1] + skin.HOT_SIZE
            for x, y, w, h in buttons:
                assert (x, w, h) == (skin.BAG_LEFT, skin.BAG_CONTENT_WIDTH, skin.BUTTON_HEIGHT)
                assert y - above == skin.PADDING, (slots, tradeskill)
                above = y + h
            assert height - (skin.BORDER + above) == skin.PADDING, (slots, tradeskill)
    # A 10-slot bag, an 8-slot one, a 4-slot one and a 10-slot tradeskill container.
    assert (heights[10, False], heights[8, False], heights[4, False], heights[10, True]) == (238, 196, 112, 260)
    # The XML's size is a 10-slot bag's (the game sets its own).
    root, window = screen(skin.CONTAINER_FILE)
    assert box(window)[2:] == bag_layout(10, False)[0]


def test_bag_buttons_are_pinned_to_the_bottom_with_their_labels_drawn_in():
    # The game moves Combine and Done 4px under the slots and leaves 36px down to share (see CONTAINER_FILE), so
    # both are pinned to the window's bottom, where the client draws them, and their XML heights are only what
    # grows its box: Done's is negative, the game's 36px being more than the paddings need.
    root, window, controls = bag_window()
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(everything(), 'Ui2DAnimation')
    assert [label for _, label, _, _ in skin.BAG_BUTTONS] == ['Combine', 'Done']
    assert (skin.BAG_COMBINE_LAYOUT_HEIGHT, skin.BAG_DONE_LAYOUT_HEIGHT) == (18, -6)
    for screen_id, label, bottom, layout_height in skin.BAG_BUTTONS:
        button = controls[screen_id]
        assert button.findtext('AutoStretch') == 'true'
        assert anchors(button) == (skin.BAG_LEFT, bottom + skin.BUTTON_HEIGHT, skin.BAG_LEFT + skin.BAG_CONTENT_WIDTH,
                                   bottom)
        assert [button.findtext(f) for f in ('TopAnchorToTop', 'BottomAnchorToTop', 'RightAnchorToLeft')] == [
            'false', 'false', 'true']
        assert box(button)[2:] == (skin.BAG_CONTENT_WIDTH, layout_height)
        assert button.findtext('Text') == '' and button.findtext('Style_Checkbox') == 'false'
        for state in button.find('ButtonDrawTemplate'):
            art = skin.button_art(skin.BAG_CONTENT_WIDTH, skin.BUTTON_HEIGHT, label, skin.BUTTON_ART[state.tag])
            assert state.text == f'TUI_{art}'
            assert cut(atlas, anims[state.text]).size == (skin.BAG_CONTENT_WIDTH, skin.BUTTON_HEIGHT)


def test_player_window_shows_hp_mana_xp_and_aa_rates_and_resists_only():
    # The user wanted only the HP and mana bars and values and the resists, abbreviated, then XP/hour, then
    # the AA rate beside it.
    # 10% narrower than the others, then 10% more (the user's requests), with the usual padding each side.
    # As wide as the hot button and actions windows (the user's request; the pet window's 177 before).
    assert skin.PLAYER_WIDTH == skin.HOT_WIDTH == skin.ACTIONS_WIDTH == 174
    assert skin.PLAYER_CONTENT_WIDTH == skin.PLAYER_WIDTH - 2 * skin.PADDING
    root, window = check_inside_frame(skin.PLAYER_FILE, skin.PLAYER_WIDTH)
    assert window.get('item') == 'PlayerWindow'
    by_id = {e.findtext('ScreenID'): e for e in parts(root).values() if e.findtext('ScreenID')}
    labels = {e.get('item'): e for e in root.iter('Label')}
    # The four gauges the client looks up; stamina and pet stay, hidden.
    assert {by_id[i].findtext('EQType') for i in ('PlayerHP', 'PlayerMana')} == {'1', '2'}
    for screen_id, eq_type in (('PlayerFatigue', '3'), ('PetHP', '16')):
        assert by_id[screen_id].findtext('EQType') == eq_type and box(by_id[screen_id])[2:] == (0, 0)
    for n, (screen_id, caption, percent_type, current_type, max_type) in enumerate((
            ('PlayerHP', 'Health', '19', '17', '18'), ('PlayerMana', 'Mana', '20', '124', '125'))):
        # The user's layout: the caption on the left and current/max on the right of one line, the bar
        # under it as in the group window, the next section two paddings under the bar (to the caption's
        # ink; the user asked for the sections set apart, like the resists from XP/hour).
        top = skin.PLAYER_SECTIONS_TOP + n * skin.PLAYER_SECTION_PITCH
        head = labels[f'TUI_PW_{screen_id}Caption']
        assert head.findtext('Text') == caption and head.findtext('AlignLeft') == 'true'
        # In the text's color: the user didn't like the subdued grey the captions had.
        assert box(head)[:2] == (skin.LEFT, top) and rgb(head, 'TextColor') == skin.CAPTION_RGB == skin.TEXT_RGB
        # Both numbers in the game's green: it colors the max HP itself, so the user had all the values
        # match it. The slash between them in the text color (the user's request). The max ends at the
        # window's padding.
        current, slash, most = (labels[f'TUI_PW_{screen_id}{part}'] for part in ('Current', 'Slash', 'Max'))
        assert current.findtext('EQType') == current_type and rgb(current, 'TextColor') == skin.VALUE_RGB == (0, 255, 0)
        assert current.findtext('AlignRight') == 'true'
        assert slash.findtext('Text') == '/' and rgb(slash, 'TextColor') == skin.TEXT_RGB
        assert most.findtext('EQType') == max_type and rgb(most, 'TextColor') == skin.VALUE_RGB
        assert most.findtext('AlignLeft') == 'true'
        cx, cy, cw, ch = box(current)
        sx, sy, sw, sh = box(slash)
        mx, my, mw, mh = box(most)
        assert cy == sy == my == top and cx + cw == sx and sx + sw == mx and mx + mw == skin.PLAYER_RIGHT
        assert cw == mw == skin.PLAYER_NUMBER_WIDTH
        # A space either side of the slash, so the numbers read apart (the user's request).
        assert sw == 4 + 2 * skin.SPACE_WIDTH and slash.findtext('AlignCenter') == 'true'
        # Your % in the middle of the line (the user's pick, so the layout stays): the game's label 19 or 20,
        # right-aligned with the drawn % after it, two paddings and a digit before the current number (at one
        # padding they ran together, then the user asked for the % nearer the caption, then one more
        # character), in the values' green (gold was tried). The % shows while your own health is above 0, so
        # always. The caption ends before it.
        percent_number = labels[f'TUI_PW_{screen_id}Percent']
        assert percent_number.findtext('EQType') == percent_type and percent_number.findtext('AlignRight') == 'true'
        assert rgb(percent_number, 'TextColor') == skin.VALUE_RGB and not percent_number.findtext('Text')
        px, py, pw, ph = box(percent_number)
        assert py == top and box(head)[0] + box(head)[2] <= px
        percent_clip = items(root, 'Screen')[f'TUI_PW_{screen_id}PercentSign_Clip']
        assert box(percent_clip) == (px + pw, top + skin.PERCENT_INK_TOP, skin.PERCENT_WIDTH,
                                     skin.PERCENT_GLYPH_HEIGHT)
        assert box(percent_clip)[0] + box(percent_clip)[2] + 2 * skin.PADDING + skin.DIGIT_WIDTH == cx
        assert skin.DIGIT_WIDTH == 7  # a character in font 3 (Arial 12px), the user's request
        # Even "100" (the number box's whole width) stays more than a padding after "Health" (36px in Arial 12).
        assert px - skin.LEFT - 36 > skin.PADDING
        percent_sign = items(root, 'Gauge')[percent_clip.find('Pieces').text]
        assert percent_sign.findtext('EQType') == '1' and rgb(percent_sign, 'FillTint') == skin.VALUE_RGB
        bar = box(by_id[screen_id])
        assert bar == (skin.LEFT, top + skin.BAR_TOP, skin.PLAYER_CONTENT_WIDTH, skin.BAR_HEIGHT)
        if n:
            above = box(by_id['PlayerHP'])
            assert 2 * skin.PADDING <= top + skin.TEXT_INK_TOP - (above[1] + above[3]) < 2 * skin.PADDING + 1
    # Mana's bar a soft blue and HP's the soft green the current HP number had at first (the user's picks).
    assert rgb(by_id['PlayerMana'], 'FillTint') == skin.MANA_RGB
    assert rgb(by_id['PlayerHP'], 'FillTint') == skin.HP_RGB == (143, 209, 158)
    # The mana bar solid, so it's exactly the group window's names' blue (the user's request); HP's softened
    # like the other bars. Both on the same track.
    anims = items(everything(), 'Ui2DAnimation')
    for screen_id, fill in (('PlayerMana', skin.WHITE), ('PlayerHP', skin.BAR_FILL)):
        template = by_id[screen_id].find('GaugeDrawTemplate')
        assert colors(anims[template.findtext('Fill')]) == {fill}
        assert template.findtext('Background') == 'TUI_PlayerTrack'
    assert skin.MANA_RGB == skin.GROUP_RGB
    # The resists: a caption in the text's color over each number, in five columns across the window.
    columns = []
    for caption, eq_type in skin.RESISTS:
        head, number_label = labels[f'TUI_PW_{caption}Caption'], labels[f'TUI_PW_{caption}']
        assert head.findtext('Text') == caption and rgb(head, 'TextColor') == skin.CAPTION_RGB
        assert head.findtext('Font') == '2' and head.findtext('AlignCenter') == 'true'
        assert number_label.findtext('EQType') == str(eq_type) and number_label.findtext('AlignCenter') == 'true'
        assert rgb(number_label, 'TextColor') == skin.VALUE_RGB  # the values' green (the user's call)
        hx, hy, hw, hh = box(head)
        assert box(number_label) == (hx, hy + hh, hw, skin.TEXT_HEIGHT)
        columns.append((hx, hw))
    assert [c for c, _ in skin.RESISTS] == ['DR', 'PR', 'MR', 'FR', 'CR']
    assert columns[0][0] == skin.LEFT and columns[-1][0] + columns[-1][1] == skin.PLAYER_RIGHT
    assert all(a[0] + a[1] == b[0] for a, b in zip(columns, columns[1:]))
    # XP/hour on its own line under Mana (the user's pick), like a section with no bar: its caption's ink two
    # paddings under the server tick, which is under the mana bar (the user asked for it less grouped with
    # Health and Mana; see the server tick test). Zeal's label 81
    # (a whole percent of a level an hour) counts regular XP only, so it stayed 0 with AA at 100%, and the
    # user had the AA rate (label 86) share the line. Each rate is a pair, its caption a padding before its
    # number (for 3 digits) and its %: "XP/h" at the line's start, "AA/h" ending at the window's padding. Lined
    # up with the columns above, XP's value sat nearer "AA/h" than its own caption ("spacing is weird"). The
    # numbers and %s in the values' green; the % shows while your own health is above 0, so always.
    tick = box(by_id['ZealTick'])
    xp_top = skin.PLAYER_XP_TOP
    assert 2 * skin.PADDING <= xp_top + skin.TEXT_INK_TOP - (tick[1] + tick[3]) < 2 * skin.PADDING + 1
    assert skin.RATE_CAPTION_WIDTH == 26  # "XP/h" and "AA/h" in Arial 12
    pairs = []
    for item, caption, eq_type, left in (
            ('ExpPerHour', 'XP/h', '81', skin.LEFT),
            ('AAPerHour', 'AA/h', '86', skin.PLAYER_RIGHT - skin.RATE_PAIR_WIDTH)):
        right = left + skin.RATE_PAIR_WIDTH
        head, rate = labels[f'TUI_PW_{item}Caption'], labels[f'TUI_PW_{item}']
        assert head.findtext('Text') == caption and rgb(head, 'TextColor') == skin.CAPTION_RGB
        assert box(head)[:2] == (left, xp_top)
        assert rate.findtext('EQType') == eq_type and rate.findtext('AlignRight') == 'true'
        assert rgb(rate, 'TextColor') == skin.VALUE_RGB and not rate.findtext('Text')
        nx, ny, nw, nh = box(rate)
        assert ny == xp_top and box(head)[0] + box(head)[2] == nx
        assert nx - left == skin.RATE_CAPTION_WIDTH + skin.PADDING
        clip = items(root, 'Screen')[f'TUI_PW_{item}Percent_Clip']
        assert box(clip) == (nx + nw, xp_top + skin.PERCENT_INK_TOP, skin.PERCENT_WIDTH, skin.PERCENT_GLYPH_HEIGHT)
        assert box(clip)[0] + box(clip)[2] == right
        percent = items(root, 'Gauge')[clip.find('Pieces').text]
        assert percent.findtext('EQType') == '1' and rgb(percent, 'FillTint') == skin.VALUE_RGB
        pairs.append((left, right))
    # The pairs read apart, the line's middle open between them.
    assert pairs[0][0] == skin.LEFT and pairs[1][1] == skin.PLAYER_RIGHT
    assert pairs[1][0] - pairs[0][1] >= 2 * skin.PADDING
    # The resist captions' ink two paddings under the XP/hour line's ink (the user asked for 6px more), the
    # same as between the sections above, so the whole window keeps one spacing.
    xp_ink_bottom = xp_top + skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT
    assert box(labels['TUI_PW_DRCaption'])[1] + skin.CAPTION_INK_TOP - xp_ink_bottom == 2 * skin.PADDING
    # The window's bottom edge a padding under the resists' numbers' ink (the drawn %'s bottom).
    numbers = box(labels['TUI_PW_DR'])
    ink_bottom = skin.BORDER + numbers[1] + skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT
    assert box(window)[3] - ink_bottom == skin.PADDING
    # Health at the top like the other windows' first lines, with no line for your name (the user's request): no
    # label shows your name (EQType 1), and the client looks none up.
    assert box(labels['TUI_PW_PlayerHPCaption'])[1] == skin.PLAYER_SECTIONS_TOP == 0
    assert all(e.findtext('EQType') != '1' for e in labels.values())
    # Nothing else: no stamina, experience bar or other stats. Health's and Mana's five labels each, the XP and AA
    # rates' two each, and the resists'.
    assert len(labels) == 2 * 5 + 2 * 2 + 2 * len(skin.RESISTS)


def test_every_player_window_value_is_the_green_the_game_gives_a_raised_value():
    # The game's label function colors a value above its base 0xff00ff00 (its color helper, 0x4365e9). It paints
    # max HP and the resists itself, whatever the skin sets: that green while raised, grey at their base, red below.
    # Every value the client fills in the player window, and every drawn %, is that green, so the rest match raised
    # stats (the user's pick over the game's grey; the percentages in gold were tried): Health's and Mana's %,
    # current and max, the XP and AA rates and the resists.
    root, _ = check_inside_frame(skin.PLAYER_FILE, skin.PLAYER_WIDTH)
    values = [e for e in root.iter('Label') if e.findtext('EQType')]
    assert len(values) == 2 * 3 + 2 + len(skin.RESISTS)
    assert all(rgb(e, 'TextColor') == skin.VALUE_RGB == (0, 255, 0) for e in values)
    gauges = items(root, 'Gauge')
    signs = [gauges[clip.find('Pieces').text] for name, clip in items(root, 'Screen').items()
             if name.endswith('_Clip')]
    assert len(signs) == 4 and all(rgb(sign, 'FillTint') == skin.VALUE_RGB for sign in signs)


# Every control of the stock raid window, which the client looks up by ScreenID (eqgame.exe's string table lists
# all but the two static labels, kept like every stock control).
RAID_IDS = {'RAID_PlayerList', 'RAID_PlayerListLabel', 'RAID_NotInGroupPlayerList', 'RAID_NotInGroupPlayerListLabel',
            'RAID_PlayerCountLabel', 'RAID_PlayerCountStringLabel', 'RAID_LevelAverageLabel',
            'RAID_LevelAverageStringLabel', 'Raid_InviteButton', 'Raid_AcceptButton', 'Raid_DisbandButton',
            'Raid_DeclineButton', 'Raid_MakeLeaderButton', 'Raid_AddLooterButton', 'Raid_RemoveLooterButton',
            'Raid_OptionsButton'}


def test_raid_window_keeps_every_control_the_client_looks_for():
    root, window = check_inside_frame(skin.RAID_FILE, skin.RAID_WIDTH)
    assert window.get('item') == 'RaidWindow'
    # A fixed size like the other windows, so it drags by its background (the user's pick): a sizable window
    # can only be dragged by a title bar in this client.
    assert window.findtext('Style_Sizable') == 'false' and window.findtext('Style_Titlebar') == 'false'
    assert box(window)[2:] == (skin.RAID_WIDTH, skin.RAID_HEIGHT)
    ids = [e.findtext('ScreenID') for e in direct_pieces(root, window)]
    assert len(ids) == len(set(ids)) and set(ids) == RAID_IDS


def test_raid_lists_show_group_name_class_and_rank_with_level_hidden():
    root, window = screen(skin.RAID_FILE)
    lists = {e.findtext('ScreenID'): e for e in root.iter('Listbox')}
    assert set(lists) == {'RAID_PlayerList', 'RAID_NotInGroupPlayerList'}
    for listbox in lists.values():
        columns = listbox.findall('Columns')
        # The client's five columns in its order; the level column has no width and no heading (the user's pick).
        assert [c.findtext('Heading') for c in columns] == ['Grp', 'Name', '', 'Class', 'Rank']
        widths = [number(c, 'Width') for c in columns]
        assert widths[2] == 0 and columns[2].find('Header') is None
        # Each as wide as its widest text in font 3 (Arial 12px) and a padding: "Grp", "Shadow Knight" and "Group
        # Leader" (the client's longest rank). Names keep the stock skin's width.
        assert (widths[0], widths[3], widths[4]) == (20 + skin.PADDING, 83 + skin.PADDING, 76 + skin.PADDING)
        assert widths[1] == 85
        # The columns and the scrollbar fill the list, which spans the window between its paddings.
        x, y, width, height = box(listbox)
        assert x == skin.LEFT and sum(widths) + skin.SCROLL_WIDTH == width == skin.RAID_WIDTH - 2 * skin.PADDING
        # Straight on the window's panel, only the slim scrollbar drawn, in the windows' font.
        assert listbox.findtext('DrawTemplate') == skin.EDIT_TEMPLATE
        assert listbox.findtext('Style_VScroll') == 'true' and listbox.findtext('Style_Border') == 'false'
        assert listbox.findtext('Font') == str(skin.TEXT_FONT) and rgb(listbox, 'TextColor') == skin.TEXT_RGB
        assert all(c.findtext('Header') == skin.LIST_HEADER for c in columns if number(c, 'Width'))
    root = everything()
    template = items(root, 'WindowDrawTemplate')[skin.EDIT_TEMPLATE]
    assert template.findtext('VSBTemplate/Thumb/Middle') == 'TUI_ThumbMiddle'
    assert {p[3] for p in pixels(decode(files()[template.findtext('Background')]))} == {0}
    # Each heading on a strip of the overlay's header tint (its white at 20, on the steps as the buttons' wash): one
    # flat piece for the header's left, middle and right, which the client repeats across the column.
    header = items(root, 'FrameTemplate')[skin.LIST_HEADER]
    assert {e.tag: e.text for e in header if not e.tag.startswith('Overlap')} == dict.fromkeys(
        ('Left', 'Middle', 'Right'), 'TUI_ListHeaderWash')
    wash = items(root, 'Ui2DAnimation')['TUI_ListHeaderWash']
    assert colors(wash) == {skin.HEADER_RGBA} == {(255, 255, 255, 17)}
    assert rect_of(wash)[3] == skin.RAID_HEADER_HEIGHT == 16  # the stock header pieces' height


def test_raid_window_follows_the_spacing_standard():
    root, window = screen(skin.RAID_FILE)
    found = {e.findtext('ScreenID'): e for e in direct_pieces(root, window)}
    grouped, caption, ungrouped = (box(found[i]) for i in (
        'RAID_PlayerList', 'RAID_NotInGroupPlayerListLabel', 'RAID_NotInGroupPlayerList'))
    # The first list's heading strip a padding from the window's edge, across and down.
    assert grouped[:2] == (skin.LEFT, skin.LEFT) and skin.BORDER + skin.LEFT == skin.PADDING
    # The caption's ink a padding under the first list (to the half pixel), and the second list a padding under the
    # caption's ink bottom, which is level with the digits' bottom.
    assert caption[0] == skin.LEFT
    assert skin.PADDING <= caption[1] + skin.TEXT_INK_TOP - (grouped[1] + grouped[3]) < skin.PADDING + 1
    assert ungrouped[1] - (caption[1] + skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT) == skin.PADDING
    # The buttons: two rows of three filling the lists' width, a padding apart and a padding under the second
    # list, and the window's edge a padding under them.
    boxes = {screen_id: box(found[screen_id]) for screen_id, *_ in skin.RAID_BUTTONS}
    rows = sorted({b[1] for b in boxes.values()})
    assert len(rows) == 2
    assert rows[0] - (ungrouped[1] + ungrouped[3]) == skin.BUTTON_ROW_GAP == skin.PADDING
    assert rows[1] - (rows[0] + skin.BUTTON_HEIGHT) == skin.BUTTON_ROW_GAP
    for top in rows:
        row = sorted({b for b in boxes.values() if b[1] == top})
        assert len(row) == 3 and {b[3] for b in row} == {skin.BUTTON_HEIGHT}
        assert row[0][0] == skin.LEFT and row[-1][0] + row[-1][2] == skin.LEFT + skin.RAID_LIST_WIDTH
        assert all(a[0] + a[2] + skin.BUTTON_GAP == b[0] for a, b in zip(row, row[1:]))
        assert max(b[2] for b in row) - min(b[2] for b in row) <= 1
    assert box(window)[3] == 2 * skin.BORDER + rows[1] + skin.BUTTON_HEIGHT + skin.BOTTOM_GAP
    assert skin.BORDER + skin.BOTTOM_GAP == skin.PADDING


def test_raid_buttons_share_spots_like_the_group_windows():
    # Every stock button (the user's pick). The client shows Accept and Decline in place of Invite and Disband
    # during an invitation, like the group window's Follow and Decline, so they share those spots.
    root, window = screen(skin.RAID_FILE)
    buttons = {b.findtext('ScreenID'): b for b in root.iter('Button')}
    assert set(buttons) == {i for i in RAID_IDS if i.startswith('Raid_')}
    assert box(buttons['Raid_AcceptButton']) == box(buttons['Raid_InviteButton'])
    assert box(buttons['Raid_DeclineButton']) == box(buttons['Raid_DisbandButton'])
    assert len({box(b) for b in buttons.values()}) == 6
    # Full words drawn in the art (the buttons' own text is empty), with the stock tooltips.
    labels = {screen_id: text for screen_id, text, *_ in skin.RAID_BUTTONS}
    assert [labels[f'Raid_{n}Button'] for n in ('Invite', 'Disband', 'MakeLeader', 'AddLooter', 'RemoveLooter',
                                                'Options')] == ['Invite', 'Disband', 'Make Leader', 'Add Looter',
                                                                'Remove Looter', 'Options']
    for screen_id, b in buttons.items():
        assert b.findtext('Text') == '' and b.findtext('TooltipReference')
        art = skin.button_art(*box(b)[2:], labels[screen_id], 'Normal')
        assert b.findtext('ButtonDrawTemplate/Normal') == f'TUI_{art}'
    assert buttons['Raid_DeclineButton'].findtext('TooltipReference') == 'Refuse an invitation to raid'


def test_raid_count_level_average_and_first_caption_are_hidden_but_still_there():
    # The user didn't want the player count or the level average, and the first list needs no caption. The
    # client looks them up (and writes the numbers), so they stay with no size and no text, in the panel's color
    # in case the client draws their text anyway.
    root, window = screen(skin.RAID_FILE)
    labels = {e.findtext('ScreenID'): e for e in root.iter('Label')}
    hidden = set(skin.RAID_HIDDEN_LABELS)
    assert hidden == {'RAID_PlayerListLabel', 'RAID_PlayerCountLabel', 'RAID_PlayerCountStringLabel',
                      'RAID_LevelAverageLabel', 'RAID_LevelAverageStringLabel'}
    assert set(labels) == hidden | {'RAID_NotInGroupPlayerListLabel'}
    for screen_id in hidden:
        assert box(labels[screen_id])[2:] == (0, 0) and not labels[screen_id].findtext('Text')
        assert rgb(labels[screen_id], 'TextColor') == skin.PANEL_RGBA[:3]
    # The second list's caption, in the captions' color.
    caption = labels['RAID_NotInGroupPlayerListLabel']
    assert caption.findtext('Text') == 'Not in a group' and rgb(caption, 'TextColor') == skin.CAPTION_RGB


# The merchant window

# Every control the client looks up in the merchant window besides its 80 slots (eqgame.exe's string table), and the
# four Project Quarm's eqgame.dll looks up for its recharge.
MERCHANT_IDS = {'MW_MerchantName', 'MerchantSlotsWnd', 'MW_SelectedItem', 'MW_Buy_Button', 'MW_Sell_Button',
                'DoneButton', 'MW_Recharge_Button', 'MW_Recharge_Charges', 'MW_Recharge_Price', 'MW_SelectedItemLabel'}


def merchant_pieces():
    """The merchant window's file, its window, and its own controls by ScreenID (not the divider, a picture)."""
    root, window = screen(skin.MERCHANT_FILE)
    return root, window, {e.findtext('ScreenID'): e for e in direct_pieces(root, window) if e.tag != 'StaticAnimation'}


def test_merchant_window_keeps_every_control_the_client_and_quarm_look_for():
    root, window = check_inside_frame(skin.MERCHANT_FILE, skin.MERCHANT_WIDTH)
    assert window.get('item') == 'MerchantWnd'
    # A fixed size like the other windows, so it drags by its background.
    assert window.findtext('Style_Sizable') == 'false'
    assert box(window)[2:] == (skin.MERCHANT_WIDTH, skin.MERCHANT_HEIGHT)
    ids = [e.findtext('ScreenID') for e in direct_pieces(root, window) if e.tag != 'StaticAnimation']
    assert len(ids) == len(set(ids)) and set(ids) == MERCHANT_IDS
    # The 80 slots are the pieces of the client's panel for them, not the window's, each its own EQType.
    panel = merchant_pieces()[2]['MerchantSlotsWnd']
    slots = direct_pieces(root, panel)
    assert panel.tag == 'Screen' and {s.tag for s in slots} == {'InvSlot'}
    assert [s.findtext('ScreenID') for s in slots] == [f'MW_MerchantSlot{n}' for n in range(80)]
    assert [number(s, 'EQType') for s in slots] == list(range(6000, 6080))


def test_merchant_slots_are_all_80_eight_across_on_the_hot_bars_squares():
    root, window, found = merchant_pieces()
    panel = found['MerchantSlotsWnd']
    # All at once, nothing to scroll (the user's pick): the panel is exactly the grid, a padding from the window's
    # top and sides, see-through on the window's panel.
    assert (skin.MERCHANT_COLUMNS, skin.MERCHANT_ROWS) == (8, 10)
    assert box(panel) == (skin.LEFT, skin.LEFT, skin.MERCHANT_CONTENT_WIDTH, skin.MERCHANT_GRID_HEIGHT)
    assert skin.LEFT + skin.MERCHANT_CONTENT_WIDTH == skin.MERCHANT_RIGHT
    assert skin.MERCHANT_WIDTH - 2 * skin.BORDER - skin.MERCHANT_RIGHT == skin.LEFT
    assert panel.findtext('Style_VScroll') == 'false' and panel.findtext('Style_Transparent') == 'true'
    assert panel.findtext('Style_Border') == 'false' and panel.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    # Placed by Location and Size: while recharging, Quarm's eqgame.dll moves the panel's bottom anchor, which only an
    # anchored panel follows.
    assert panel.find('AutoStretch') is None
    # The hot bar's 36px squares, a padding apart, left to right then down; empty ones the plain square.
    slots = direct_pieces(root, panel)
    for n, slot in enumerate(slots):
        assert box(slot) == (n % 8 * skin.HOT_PITCH, n // 8 * skin.HOT_PITCH, skin.HOT_SIZE, skin.HOT_SIZE)
        assert slot.findtext('Background') == 'TUI_HotButtonNormal'
    x, y, width, height = box(slots[-1])
    assert (x + width, y + height) == box(panel)[2:]


def test_merchant_window_follows_the_spacing_standard():
    root, window, found = merchant_pieces()
    boxes = {screen_id: box(e) for screen_id, e in found.items()}
    panel, item = boxes['MerchantSlotsWnd'], boxes['MW_SelectedItem']
    # Under the grid, the Effects window's divider across the content row, a padding from it (the user's request,
    # to set the considered item apart from the slots).
    dividers = [e for e in direct_pieces(root, window) if e.tag == 'StaticAnimation']
    assert len(dividers) == 1
    divider = box(dividers[0])
    assert divider == (skin.LEFT, panel[1] + panel[3] + skin.PADDING, skin.MERCHANT_CONTENT_WIDTH, 1)
    line = cut(decode(files()[skin.PIECES_TEXTURE]),
               items(everything(), 'Ui2DAnimation')[dividers[0].findtext('Animation')])
    assert line.size == divider[2:] and set(pixels(line)) == {skin.ROW_DIVIDER_RGBA}
    # The considered item's square a padding under the divider, at the window's padding.
    assert item == (skin.LEFT, divider[1] + divider[3] + skin.PADDING, skin.HOT_SIZE, skin.HOT_SIZE)
    # The recharge text a padding after the square and a padding before Recharge, which ends at the window's padding
    # over Done, as wide.
    charges, price, recharge = (boxes[i] for i in ('MW_Recharge_Charges', 'MW_Recharge_Price', 'MW_Recharge_Button'))
    buy, sell, done = boxes['MW_Buy_Button'], boxes['MW_Sell_Button'], boxes['DoneButton']
    assert charges[0] == price[0] == item[0] + item[2] + skin.PADDING and charges[2] == price[2]
    assert charges[0] + charges[2] + skin.PADDING == recharge[0]
    assert (recharge[0], recharge[2]) == (done[0], done[2]) and done[0] + done[2] == skin.MERCHANT_RIGHT
    # The two lines stacked on their line height, the ink of both (the first's top to the second's digits' bottom)
    # centered on the square; Recharge centered on it too.
    assert price[1] == charges[1] + skin.TEXT_HEIGHT
    assert abs((charges[1] + price[1]) / 2 + skin.DIGITS_INK_MIDDLE - (item[1] + skin.HOT_SIZE / 2)) <= 0.5
    assert recharge[1] - item[1] == item[1] + item[3] - (recharge[1] + recharge[3])
    # The item label, which Quarm shows instead of the recharge text, covers both lines.
    assert boxes['MW_SelectedItemLabel'] == (charges[0], charges[1], charges[2], 2 * skin.TEXT_HEIGHT)
    # Buy (or Sell, in the same spot) and Done fill the row a padding under the band, a padding apart, and the
    # window's edge is a padding under them.
    assert buy == sell and buy[0] == skin.LEFT and buy[0] + buy[2] + skin.BUTTON_GAP == done[0]
    assert buy[1] == done[1] == item[1] + item[3] + skin.BUTTON_ROW_GAP and skin.BUTTON_ROW_GAP == skin.PADDING
    assert {buy[3], done[3], recharge[3]} == {skin.TEXT_BUTTON_HEIGHT}
    assert box(window)[3] == 2 * skin.BORDER + done[1] + skin.TEXT_BUTTON_HEIGHT + skin.BOTTOM_GAP
    assert skin.BORDER + skin.BOTTOM_GAP == skin.PADDING


def test_merchant_recharge_group_shares_the_item_labels_spot_and_leaves_quarm_its_tooltip():
    root, window, found = merchant_pieces()
    # Quarm shows the charges, the next charge's price and Recharge while one of your items with charges is
    # selected, and the item label otherwise. It writes the two lines and never the label, which says nothing (the
    # user's pick).
    for screen_id in ('MW_SelectedItemLabel', 'MW_Recharge_Charges', 'MW_Recharge_Price'):
        text = found[screen_id]
        assert text.tag == 'Label' and text.findtext('Text') == '' and text.find('EQType') is None
        assert number(text, 'Font') == skin.TEXT_FONT and rgb(text, 'TextColor') == skin.TEXT_RGB
    # Every button is the confirmation dialog's kind (the user's pick). Recharge has no tooltip of ours: Quarm writes
    # the price per charge there.
    check_confirmation_button(found['MW_Recharge_Button'], 'Recharge')
    # Buy and Sell share a spot (the client shows one), each with the client's own tooltip; Done has none.
    buttons = {screen_id: (text, tooltip) for screen_id, text, tooltip, _ in skin.MERCHANT_BUTTONS}
    assert buttons == {'MW_Buy_Button': ('Buy', 'Purchase considered item'),
                       'MW_Sell_Button': ('Sell', 'Sell considered item'), 'DoneButton': ('Done', None)}
    for screen_id, (text, tooltip) in buttons.items():
        check_confirmation_button(found[screen_id], text, tooltip)
    # The considered item's square: the plain square, with the item's icon over all of it (the stock item icons,
    # which the client sets).
    item = found['MW_SelectedItem']
    assert item.tag == 'Button' and item.findtext('TooltipReference') == 'Item being considered'
    assert item.findtext('ButtonDrawTemplate/Normal') == 'TUI_HotButtonNormal'
    assert item.findtext('ButtonDrawTemplate/NormalDecal') == skin.ITEM_ICONS == 'A_DragItem'
    assert (number(item, 'DecalOffset/X'), number(item, 'DecalOffset/Y')) == (0, 0)
    assert (number(item, 'DecalSize/CX'), number(item, 'DecalSize/CY')) == (skin.HOT_SIZE, skin.HOT_SIZE)


def test_merchant_name_is_hidden_but_still_there():
    # The user didn't want the merchant's name. The client looks it up and writes it, so it stays with no size and
    # no text, in the panel's color in case the client draws its text anyway.
    name = merchant_pieces()[2]['MW_MerchantName']
    assert name.tag == 'Label' and box(name)[2:] == (0, 0) and not name.findtext('Text')
    assert rgb(name, 'TextColor') == skin.PANEL_RGBA[:3]


def test_confirmation_dialog_keeps_every_control_the_client_looks_for():
    # eqgame.exe looks up the text and the three buttons. default's static Text1 is in no skin's window and not in
    # eqgame.exe, so it's left out. As wide as the window selector (the user's pick), with no title bar, and the
    # other windows' frame: a red edge was tried and removed (the user).
    root, window = check_inside_frame(skin.CONFIRM_FILE, skin.CONFIRM_WIDTH)
    assert window.get('item') == 'ConfirmationDialogBox' and window.find('Text') is None
    assert window.findtext('Style_Sizable') == 'false' and window.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    assert box(window)[2:] == (skin.SELECTOR_WIDTH, skin.CONFIRM_HEIGHT) == (262, 94)
    ids = [e.findtext('ScreenID') for e in direct_pieces(root, window)]
    assert ids == ['TextOutput', 'Yes_Button', 'No_Button', 'OK_Button']


def test_confirmation_text_has_three_lines_with_a_dialogs_room_around_it():
    # Room for three lines: every common message takes two, the Sacrifice warning three (the user's pick). A dialog
    # keeps two paddings inside (the user asked for "better spacing" in dialogs and picked 12px): the first line's
    # ink and its sides that far from the window's edge. Nothing of its own drawn, like the raid lists, and no
    # scrollbar, as in the stock skin.
    root, window = screen(skin.CONFIRM_FILE)
    text = direct_pieces(root, window)[0]
    assert text.tag == 'STMLbox'
    assert skin.DIALOG_PADDING == 2 * skin.PADDING == skin.BORDER + skin.DIALOG_LEFT
    x, y, width, height = box(text)
    assert (x, width, height) == (skin.DIALOG_LEFT, skin.CONFIRM_CONTENT_WIDTH, 3 * skin.TEXT_HEIGHT)
    assert x + width == skin.CONFIRM_RIGHT == skin.CONFIRM_WIDTH - 2 * skin.BORDER - skin.DIALOG_LEFT
    assert skin.DIALOG_PADDING <= skin.BORDER + y + skin.TEXT_INK_TOP < skin.DIALOG_PADDING + 1
    assert text.findtext('Font') == str(skin.TEXT_FONT) and text.findtext('DrawTemplate') == skin.EDIT_TEMPLATE
    assert text.findtext('Style_Transparent') == 'true' and text.findtext('Style_Border') == 'false'
    assert text.findtext('Style_VScroll') == text.findtext('Style_HScroll') == 'false'


def test_confirmation_buttons_are_the_actions_windows_with_a_dialogs_room_around_them():
    # Yes and No fill the row a padding apart; the client shows OK alone, in the middle at their width (the user's
    # pick). The row two paddings under the last line's digits, and the window's edge two paddings under it (a
    # dialog's room).
    root, window = screen(skin.CONFIRM_FILE)
    buttons = {e.findtext('ScreenID'): e for e in root.iter('Button')}
    yes, no, ok = (box(buttons[i]) for i in ('Yes_Button', 'No_Button', 'OK_Button'))
    text = box(direct_pieces(root, window)[0])
    last_line = text[1] + 2 * skin.TEXT_HEIGHT
    assert {yes[1], no[1], ok[1]} == {last_line + skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT
                                      + skin.DIALOG_PADDING}
    assert {yes[3], no[3], ok[3]} == {skin.TEXT_BUTTON_HEIGHT}
    assert yes[0] == skin.DIALOG_LEFT and no[0] + no[2] == skin.CONFIRM_RIGHT
    assert yes[0] + yes[2] + skin.BUTTON_GAP == no[0] and abs(yes[2] - no[2]) <= 1
    assert ok[2] == yes[2] and ok[0] - skin.DIALOG_LEFT == skin.CONFIRM_RIGHT - (ok[0] + ok[2]) == 61
    assert box(window)[3] - skin.BORDER - (yes[1] + yes[3]) == skin.DIALOG_PADDING
    # As big as the Actions window's buttons, their names their own text in its font (the user liked those "and
    # their text size": "confirmation boxes are important"), over the plain wash.
    camp = parts(parse(skin.ACTIONS_FILE))['TUI_AW_AMP_CampButton']
    for screen_id, name, *_ in skin.CONFIRM_BUTTONS:
        b = buttons[screen_id]
        assert b.findtext('Text') == name and b.find('TooltipReference') is None
        assert b.findtext('Font') == camp.findtext('Font') == str(skin.ACTION_FONT) == '2'
        assert rgb(b, 'TextColor') == rgb(camp, 'TextColor') == skin.TEXT_RGB
        assert box(b)[3] == box(camp)[3]
        assert b.findtext('ButtonDrawTemplate/Normal') == f'TUI_{skin.button_art(*box(b)[2:], "", "Normal")}'
    assert [name for _, name, *_ in skin.CONFIRM_BUTTONS] == ['Yes', 'No', 'OK']


def item_inside(height=None):
    """The item window's inside under its title bar, where its controls are placed (the window within its border,
    less the bar), at its own height or the one given."""
    height = skin.ITEM_HEIGHT if height is None else height
    return skin.ITEM_WIDTH - 2 * skin.BORDER, height - 2 * skin.BORDER - skin.ITEM_TITLE_HEIGHT


def test_item_window_keeps_only_the_stock_windows_two_controls_in_its_order():
    # eqgame.exe looks up only the text and the icon, and Zeal links just those two, in this order, as the children
    # of its own item windows (ZealItemDisplay0 to 4), so nothing else may be added. The user's picks: a title bar
    # with the name in font 3 and a Close button on it, no minimize box, and a fixed size (Zeal keeps no size for
    # its windows anyway).
    root, window = screen(skin.ITEM_FILE)
    assert window.get('item') == 'ItemDisplayWindow'
    assert [(e.tag, e.findtext('ScreenID')) for e in direct_pieces(root, window)] == [
        ('STMLbox', 'ItemDescription'), ('Button', 'IconButton')]
    assert window.findtext('Style_Titlebar') == window.findtext('Style_Closebox') == 'true'
    assert window.findtext('Style_Minimizebox') == window.findtext('Style_Sizable') == 'false'
    assert window.findtext('DrawTemplate') == skin.ITEM_TEMPLATE
    assert window.findtext('Font') == str(skin.TEXT_FONT) == '3'
    assert box(window)[2:] == (skin.ITEM_WIDTH, skin.ITEM_HEIGHT) == (400, 210)
    # The game writes the item's name over its own placeholder. The stock window's tooltip.
    assert window.findtext('Text') == 'Item Display'
    assert window.findtext('TooltipReference') == 'This is an Item Display window'


def test_item_title_bar_is_the_chat_bars_look_with_the_dialogs_close_button():
    # The usual frame with the chat bar's look (the panel, a row divider along the bottom), tall enough for the
    # Close button (the user's pick; the close box is the only button the game lets close the window). The quantity
    # window has the same.
    templates = items(everything(), 'WindowDrawTemplate')
    item, usual = templates[skin.ITEM_TEMPLATE], templates[skin.FRAME_TEMPLATE]
    assert item.findtext('Background') == usual.findtext('Background') == skin.BACKGROUND_TEXTURE
    assert [(e.tag, e.text) for e in item.find('Border')] == [(e.tag, e.text) for e in usual.find('Border')]
    assert {item.findtext(f'Titlebar/{side}') for side in ('Left', 'Middle', 'Right')} == {'TUI_ItemTitleBar'}
    anims = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')
    atlas = decode(files()[skin.PIECES_TEXTURE])
    bar = cut(atlas, anims['TUI_ItemTitleBar'])
    assert bar.size == (skin.TITLE_PIECE_WIDTH, skin.ITEM_TITLE_HEIGHT) and skin.ITEM_TITLE_HEIGHT == 29
    rows = [set(bar.getpixel((x, y)) for x in range(bar.width)) for y in range(bar.height)]
    assert rows[:-1] == [{skin.PANEL_RGBA}] * (skin.ITEM_TITLE_HEIGHT - 1) and rows[-1] == {skin.TITLE_DIVIDER_RGBA}
    # The close box in every state: clear rows, then the Close button, the dialogs' plain wash at the size of the
    # quantity window's Accept, which it sits over there. Its name is painted on in the text's color (the game writes
    # nothing on a close box; see CLOSE_INK), centered across it, dimmed like the lettering while disabled.
    assert skin.CLOSE_WIDTH == skin.QUANTITY_ROW_WIDTHS[1] == 72
    left, top = skin.CLOSE_INK_AT
    ink_width = len(skin.CLOSE_INK[0])
    assert {len(row) for row in skin.CLOSE_INK} == {ink_width} and abs(left + ink_width / 2 - skin.CLOSE_WIDTH / 2) <= 0.5
    close = item.find('CloseBox')
    assert [e.tag for e in close] == list(skin.BUTTON_STATES)
    for state in close:
        look = skin.BUTTON_ART[state.tag]
        assert state.text == f'TUI_ItemClose{look}'
        art = cut(atlas, anims[state.text])
        assert art.size == (skin.CLOSE_WIDTH, skin.CLOSE_CLEAR + skin.TEXT_BUTTON_HEIGHT)
        assert {art.getpixel((x, y))[3] for x in range(art.width) for y in range(skin.CLOSE_CLEAR)} == {0}
        button = art.crop((0, skin.CLOSE_CLEAR, art.width, art.height))
        wash = as_image(skin.labeled_button_art(skin.CLOSE_WIDTH, skin.TEXT_BUTTON_HEIGHT, '', look))
        name_color = (*skin.TEXT_RGB, skin.LABEL_ALPHA[look])
        for y in range(button.height):
            for x in range(button.width):
                inked = 0 <= y - top < len(skin.CLOSE_INK) and 0 <= x - left < ink_width
                coverage = int(skin.CLOSE_INK[y - top][x - left], 16) / 15 if inked else 0
                expected = skin.snapped(skin.over(name_color, coverage, wash.getpixel((x, y))))
                assert button.getpixel((x, y)) == expected, (look, x, y)
    # The other windows keep the stock box, which none of them shows.
    assert usual.findtext('CloseBox/Normal') == 'A_CloseBtnNormal'


def test_item_window_follows_the_spacing_standard_where_the_game_lets_it():
    # The game draws the close box at its art's size, its right edge CLOSE_BOX_INSET in from the inside's right
    # edge and its top CLOSE_BOX_TOP under the title bar's, which starts at the inside's top (eqgame.exe, 0x57165a).
    b = skin.BORDER
    button_top = b + skin.CLOSE_BOX_TOP + skin.CLOSE_CLEAR  # the visible button, under its clear rows
    assert button_top == skin.PADDING
    # Forced: the game's inset leaves the button's right edge 11px from the window's (the user accepted it).
    assert skin.ITEM_WIDTH - (skin.ITEM_WIDTH - b - skin.CLOSE_BOX_INSET) == 11
    # A padding under the button, the divider (the bar's bottom row), then a padding to the icon.
    divider = b + skin.ITEM_TITLE_HEIGHT - 1
    assert divider - (button_top + skin.TEXT_BUTTON_HEIGHT) == skin.PADDING
    root, window = screen(skin.ITEM_FILE)
    text, icon = direct_pieces(root, window)
    top = b + skin.ITEM_TITLE_HEIGHT  # the controls' inside, in the window
    ix, iy, iw, ih = anchored_rect(icon, item_inside())
    assert (iw, ih) == drawn_size(icon) == (skin.ITEM_ICON, skin.ITEM_ICON)
    assert b + ix == skin.PADDING and top + iy - (divider + 1) == skin.PADDING
    # The text a padding after the icon, its box (the scrollbar in it too) a padding from the right and bottom
    # edges, and its first line's ink level with the icon's top, if the box draws its first line at its top like a
    # label.
    tx, ty, tw, th = anchored_rect(text, item_inside())
    assert tx - (ix + iw) == skin.PADDING and tx == skin.ITEM_TEXT_X
    assert skin.ITEM_WIDTH - (b + tx + tw) == skin.PADDING and tx + tw == skin.ITEM_RIGHT
    assert skin.ITEM_HEIGHT - (top + ty + th) == skin.PADDING
    assert abs(ty + skin.TEXT_INK_TOP - iy) <= 0.5
    assert th == skin.ITEM_TEXT_LINES * skin.TEXT_HEIGHT == 168
    # Anchored like the stock skin's: at the old sizable window's 400x190, which the ini keeps, the text is only
    # shorter.
    assert anchored_rect(text, item_inside(190)) == (tx, ty, tw, th - (skin.ITEM_HEIGHT - 190))
    assert anchored_rect(icon, item_inside(190)) == (ix, iy, iw, ih)


def test_item_icon_and_text_take_what_the_game_puts_there():
    root, window = screen(skin.ITEM_FILE)
    text, icon = direct_pieces(root, window)
    # The game makes an item's icon the button's own Normal and a spell's its decal, both 40px (A_DragItem and
    # A_SpellIcons cells), so each draws at its own size. The XML's are the stock window's, never shown.
    assert icon.findtext('ButtonDrawTemplate/Normal') == 'TUI_Clear'
    assert icon.findtext('ButtonDrawTemplate/NormalDecal') == skin.BUFF_ICONS
    assert (number(icon, 'DecalOffset/X', None), number(icon, 'DecalOffset/Y', None)) == (0, 0)
    assert (number(icon, 'DecalSize/CX'), number(icon, 'DecalSize/CY')) == (skin.ITEM_ICON, skin.ITEM_ICON) == (40, 40)
    assert icon.findtext('Style_Checkbox') == 'false' and icon.find('TooltipReference') is None
    # The text straight on the panel with our slim scrollbar, like the raid lists; the game writes it, in its own
    # colors (SIDL gives an STMLbox no text color).
    assert text.findtext('Font') == str(skin.TEXT_FONT) and text.findtext('DrawTemplate') == skin.EDIT_TEMPLATE
    assert text.findtext('Style_Transparent') == 'true' and text.findtext('Style_Border') == 'false'
    assert text.findtext('Style_VScroll') == 'true' and text.findtext('Style_HScroll') == 'false'
    assert text.find('Text') is None and text.find('TextColor') is None


def quantity_parts():
    root, window = screen(skin.QUANTITY_FILE)
    return root, window, direct_pieces(root, window)


def test_quantity_window_keeps_every_control_the_client_looks_for():
    # eqgame.exe looks up the slider, the number field and Accept, and uses the first two unchecked: a missing one
    # would crash the game. The field's strip is ours, with no ScreenID. As wide as the hot button window, with the
    # item window's title bar and Close (the user's pick): the close box is the only button the game lets close it,
    # and Esc closes it too. No title for the game to write, which it would center under Close: the name is in the
    # bar's art (see the next test), so the window needs no font either.
    root, window = check_inside_frame(skin.QUANTITY_FILE, skin.QUANTITY_WIDTH, bar=skin.ITEM_TITLE_HEIGHT)
    assert window.get('item') == 'QuantityWnd'
    assert window.find('Text') is None and window.find('Font') is None
    assert window.findtext('Style_Titlebar') == window.findtext('Style_Closebox') == 'true'
    assert window.findtext('Style_Minimizebox') == window.findtext('Style_Sizable') == 'false'
    assert window.findtext('DrawTemplate') == skin.QUANTITY_TEMPLATE
    assert box(window)[2:] == (skin.HOT_WIDTH, skin.QUANTITY_HEIGHT) == (174, 104)
    _, _, pieces = quantity_parts()
    assert [(e.tag, e.findtext('ScreenID')) for e in pieces] == [
        ('Slider', 'QTYW_Slider'), ('Screen', None), ('Editbox', 'QTYW_SliderInput'), ('Button', 'QTYW_Accept_Button')]


def test_quantity_window_has_a_dialogs_room_around_the_slider_and_the_row_under_it():
    # The user picked the dialog padding: the knob two paddings under the title bar's line and from the window's side
    # edges, the row under it two paddings further down, and the window's edge two paddings under the row. The slider
    # spans the row, and the field and Accept each take half of it, a padding apart.
    _, window, (slider, strip, number_box, accept) = quantity_parts()
    edge = skin.BORDER
    top = edge + skin.ITEM_TITLE_HEIGHT  # the controls' inside, in the window, under the bar's line
    sx, sy, sw, sh = box(slider)
    assert edge + sx == sy == skin.DIALOG_PADDING and sx + sw == skin.QUANTITY_RIGHT
    assert sh == skin.SLIDER_HEIGHT  # the knob's height: the slider shows nothing above or below it
    fx, fy, fw, fh = box(strip)
    ax, ay, aw, ah = box(accept)
    assert fy == ay == sy + sh + skin.DIALOG_PADDING
    assert fx == skin.DIALOG_LEFT and fx + fw + skin.BUTTON_GAP == ax and ax + aw == skin.QUANTITY_RIGHT
    assert fw == aw == 72 and fh == ah == skin.INPUT_HEIGHT == skin.TEXT_BUTTON_HEIGHT
    assert box(window)[3] - (top + ay + ah) == skin.DIALOG_PADDING
    # Close on the bar, Accept's size, a pixel further right than Accept: the game's inset (see the item window).
    width = box(window)[2]
    close_right = width - edge - skin.CLOSE_BOX_INSET
    assert skin.CLOSE_WIDTH == aw and close_right - (edge + ax + aw) == 1


def test_quantity_title_bar_is_the_item_windows_with_the_name_painted_at_its_left():
    # The game centers a window's title across its bar, so in this narrow window it ran under Close. The template is
    # the item window's but for the bar's left piece, which has the name painted on in the text's color.
    templates = items(everything(), 'WindowDrawTemplate')
    quantity, item = templates[skin.QUANTITY_TEMPLATE], templates[skin.ITEM_TEMPLATE]
    for part in ('Border', 'CloseBox'):
        assert [(e.tag, e.text) for e in quantity.find(part)] == [(e.tag, e.text) for e in item.find(part)], part
    assert quantity.findtext('Background') == item.findtext('Background')
    assert [(e.tag, e.text) for e in quantity.find('Titlebar')] == [
        (e.tag, 'TUI_QuantityTitle' if e.tag == 'Left' else e.text) for e in item.find('Titlebar')]
    anims = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')
    atlas = decode(files()[skin.PIECES_TEXTURE])
    bar, piece = cut(atlas, anims['TUI_ItemTitleBar']), cut(atlas, anims['TUI_QuantityTitle'])
    left, top = skin.QUANTITY_TITLE_INK_AT
    ink_width, ink_height = len(skin.QUANTITY_TITLE_INK[0]), len(skin.QUANTITY_TITLE_INK)
    assert {len(row) for row in skin.QUANTITY_TITLE_INK} == {ink_width}
    assert piece.size == (left + ink_width, skin.ITEM_TITLE_HEIGHT)
    for y in range(piece.height):
        for x in range(piece.width):
            inked = 0 <= y - top < ink_height and 0 <= x - left < ink_width
            coverage = int(skin.QUANTITY_TITLE_INK[y - top][x - left], 16) / 15 if inked else 0
            under = bar.getpixel((x % bar.width, y))
            assert piece.getpixel((x, y)) == skin.snapped(skin.over((*skin.TEXT_RGB, 255), coverage, under)), (x, y)
    # The ink a dialog padding from the window's left and top edges, level with the slider's left edge.
    b = skin.BORDER
    _, window, (slider, *_) = quantity_parts()
    assert b + left == b + top == skin.DIALOG_PADDING and left == box(slider)[0]
    # Its capitals (all but the y's two rows of tail) share Close's name's middle, down the bar.
    close_ink_top = skin.CLOSE_BOX_TOP + skin.CLOSE_CLEAR + skin.CLOSE_INK_AT[1]
    assert top + (ink_height - 2) / 2 == close_ink_top + len(skin.CLOSE_INK) / 2
    # Well clear of Close, whose left edge is its art's width in from its right.
    close_left = box(window)[2] - b - skin.CLOSE_BOX_INSET - skin.CLOSE_WIDTH
    assert close_left - (b + left + ink_width) >= skin.DIALOG_PADDING


def test_quantity_slider_is_a_knob_on_the_bars_faint_track():
    # From eqgame.exe: the knob's left edge goes from the left cap's width to the slider's width less the right cap's,
    # and its top is the track's. So the left cap has no width and the right cap is the knob's, which keeps the knob
    # inside the slider at both ends; the track fills the rest, drawn at its own size (the client stretches it to that
    # width). Each is as tall as the knob, with the bars' faint 3px track across its middle.
    root = everything()
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(root, 'Ui2DAnimation')
    template = items(root, 'SliderDrawTemplate')[skin.SLIDER_TEMPLATE]
    knob = template.find('Thumb')
    assert [e.tag for e in knob] == list(skin.BUTTON_STATES)
    assert [e.text for e in knob] == [f'TUI_SliderKnob{skin.BUTTON_ART[s]}' for s in skin.BUTTON_STATES]
    _, _, (slider, *_) = quantity_parts()
    width, height = box(slider)[2:]
    track, right, left = (anims[template.findtext(part)] for part in ('Background', 'EndCapRight', 'EndCapLeft'))
    assert rect_of(left)[2:] == (0, height)
    assert rect_of(right)[2:] == (skin.SLIDER_KNOB_WIDTH, height)
    assert rect_of(track)[2:] == (width - skin.SLIDER_KNOB_WIDTH, height)
    clear = [(255, 255, 255, 0)] * skin.SLIDER_TRACK_TOP
    column = clear + [skin.EDGE_FADED] * skin.TWIN_BAR_HEIGHT + clear  # centered on the knob
    assert len(column) == height
    for piece in (track, right):
        image = cut(atlas, piece)
        for x in range(image.width):
            assert [image.getpixel((x, y)) for y in range(height)] == column
    # The knob is a small button in the buttons' looks: the wash at rest, slate when pointed at, darker while
    # dragged, and solid in every state, so the track never shows through it.
    art = {state: cut(atlas, anims[f'TUI_SliderKnob{state}']) for state in skin.BUTTON_LOOKS}
    for state, image in art.items():
        assert image.size == (skin.SLIDER_KNOB_WIDTH, height)
        assert {a for *_, a in pixels(image)} == {255}, state
    middle = (skin.SLIDER_KNOB_WIDTH // 2, height // 2)
    assert art['Normal'].getpixel(middle) == skin.snapped(skin.over(skin.BUTTON_LOOKS['Normal'][0], 1, skin.PANEL_RGBA))
    assert art['Flyby'].getpixel(middle) == skin.BUTTON_LOOKS['Flyby'][0]
    assert sum(art['Pressed'].getpixel(middle)[:3]) < sum(art['Flyby'].getpixel(middle)[:3])


def test_quantity_field_is_the_chat_inputs_strip_and_accept_the_dialogs_button():
    # The number sits on the chat input's strip, inset as far as there, in the text's color; the box itself draws
    # nothing. Accept is the confirmation dialog's button: its name its own text in the Actions window's font, over the
    # plain wash, with no tooltip (the stock one has none).
    _, _, (slider, strip, number_box, accept) = quantity_parts()
    assert strip.findtext('DrawTemplate') == skin.FIELD_TEMPLATE and strip.findtext('Style_Border') == 'true'
    fx, fy, fw, fh = box(strip)
    assert box(number_box) == (fx + skin.FIELD_PADDING, fy, fw - 2 * skin.FIELD_PADDING, fh)
    assert number_box.findtext('DrawTemplate') == skin.EDIT_TEMPLATE
    assert number_box.findtext('Style_Transparent') == 'true' and number_box.findtext('Style_Border') == 'false'
    assert number_box.findtext('Font') == str(skin.TEXT_FONT) and rgb(number_box, 'TextColor') == skin.TEXT_RGB
    confirm_yes = {e.findtext('ScreenID'): e for e in parse(skin.CONFIRM_FILE).iter('Button')}['Yes_Button']
    assert accept.findtext('Text') == 'Accept' and accept.find('TooltipReference') is None
    assert accept.findtext('Font') == confirm_yes.findtext('Font') == str(skin.ACTION_FONT)
    assert rgb(accept, 'TextColor') == rgb(confirm_yes, 'TextColor') == skin.TEXT_RGB
    assert box(accept)[3] == box(confirm_yes)[3]
    assert accept.findtext('ButtonDrawTemplate/Normal') == f'TUI_{skin.button_art(*box(accept)[2:], "", "Normal")}'


def give_parts():
    root, window = screen(skin.GIVE_FILE)
    return root, window, {e.findtext('ScreenID'): e for e in direct_pieces(root, window)}


def check_confirmation_button(button, name, tooltip=None):
    """button is the confirmation dialog's kind (the user's pick, where the lettering read too small): its name its own
    text in the Actions window's font and the text's color, as tall as Yes, on the plain wash at its size, with tooltip
    (none unless given)."""
    yes = {e.findtext('ScreenID'): e for e in parse(skin.CONFIRM_FILE).iter('Button')}['Yes_Button']
    assert button.findtext('Text') == name and button.findtext('TooltipReference') == tooltip
    assert button.findtext('Font') == yes.findtext('Font') == str(skin.ACTION_FONT)
    assert rgb(button, 'TextColor') == rgb(yes, 'TextColor') == skin.TEXT_RGB
    assert box(button)[3] == box(yes)[3] == skin.TEXT_BUTTON_HEIGHT
    assert button.findtext('ButtonDrawTemplate/Normal') == f'TUI_{skin.button_art(*box(button)[2:], "", "Normal")}'


def check_coin_caption(root, window, coin, caption):
    """The piece drawn right after the coin box is its coin's name: a label over the box a padding in from its left, in
    the amount's font and the text's color."""
    pieces = direct_pieces(root, window)
    label = pieces[pieces.index(coin) + 1]
    x, y = box(coin)[:2]
    assert label.tag == 'Label' and label.find('ScreenID') is None and label.find('EQType') is None
    assert label.findtext('Text') == caption and label.findtext('Font') == coin.findtext('Font') == str(skin.TEXT_FONT)
    assert rgb(label, 'TextColor') == skin.TEXT_RGB and label.findtext('NoWrap') == 'true'
    assert box(label) == (x + skin.PADDING, y + skin.COIN_CAPTION_TOP, skin.COIN_CAPTION_WIDTH, skin.TEXT_HEIGHT)


def test_give_window_keeps_every_control_the_client_looks_for():
    # eqgame.exe looks up the NPC's name, the four item slots, the four coin buttons, Give and Cancel, and nothing
    # else: all of the stock window's controls, every one shown, each coin box followed by its name, and a divider of
    # ours over the buttons. As wide as the hot button window (the user's pick, so Give and Cancel have room), with no
    # title bar or close box (it drags by its background, and Cancel closes it).
    root, window = check_inside_frame(skin.GIVE_FILE, skin.GIVE_WIDTH)
    assert window.get('item') == 'GiveWnd' and window.findtext('Text') == 'Give'
    assert window.findtext('Style_Sizable') == window.findtext('Style_Closebox') == 'false'
    assert window.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    assert box(window)[2:] == (skin.GIVE_WIDTH, skin.GIVE_HEIGHT) == (174, 150)
    assert skin.GIVE_WIDTH == skin.HOT_WIDTH
    pieces = direct_pieces(root, window)
    assert [(e.tag, e.findtext('ScreenID')) for e in pieces] == [
        ('Label', 'GVW_NPCName'), *(('InvSlot', f'GVW_MyItemSlot{n}') for n in range(4)),
        *(piece for n in range(4) for piece in (('Button', f'GVW_MyMoney{n}'), ('Label', None))),
        ('StaticAnimation', None), ('Button', 'GVW_Give_Button'), ('Button', 'GVW_Cancel_Button')]
    assert [number(e, 'EQType') for e in pieces if e.tag == 'InvSlot'] == [3000, 3001, 3002, 3003]
    assert all(box(e)[2:] != (0, 0) for e in pieces)


def test_give_window_follows_the_spacing_standard():
    root, window, found = give_parts()
    b = skin.BORDER
    # The name's line at the inside's top, across the content row: its ink starts 7.5px under the window's edge, the
    # closest the frame allows (a label placed into it isn't drawn), as in the player window.
    name = box(found['GVW_NPCName'])
    assert name == (skin.LEFT, 0, skin.GIVE_CONTENT_WIDTH, skin.TEXT_HEIGHT)
    assert b + name[1] + skin.TEXT_INK_TOP == 7.5
    # The slots in one row in reading order (the user's pick), a padding under the name's capitals and digits, on the
    # hot bar's squares a padding apart, filling the row from the window's padding to its padding.
    top = name[1] + skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT + skin.PADDING
    slots = [box(found[f'GVW_MyItemSlot{n}']) for n in range(4)]
    assert slots == [(skin.LEFT + n * skin.HOT_PITCH, top, skin.HOT_SIZE, skin.HOT_SIZE) for n in range(4)]
    assert slots[-1][0] + skin.HOT_SIZE == skin.GIVE_RIGHT
    assert skin.GIVE_WIDTH - 2 * b - skin.GIVE_RIGHT == skin.LEFT and b + skin.LEFT == skin.PADDING
    # The coins two across a padding apart, platinum to copper in reading order (pp gp, then sp cp: the user's pick), a
    # padding under the slots, each two slots wide, so the pair fills the content row.
    coins = [box(found[f'GVW_MyMoney{n}']) for n in range(4)]
    coins_top = slots[0][1] + skin.HOT_SIZE + skin.BUTTON_ROW_GAP
    pitch = skin.COIN_WIDTH + skin.BUTTON_GAP, skin.COIN_HEIGHT + skin.BUTTON_ROW_GAP
    assert coins == [(skin.LEFT + n % 2 * pitch[0], coins_top + n // 2 * pitch[1], skin.COIN_WIDTH,
                      skin.TEXT_BUTTON_HEIGHT) for n in range(4)]
    assert coins[1][0] + coins[1][2] == skin.GIVE_RIGHT
    # The row divider across the content row a padding under the coins (the user's request), in its color.
    [divider] = [e for e in direct_pieces(root, window) if e.tag == 'StaticAnimation']
    line_box = box(divider)
    assert line_box == (skin.LEFT, coins[-1][1] + coins[-1][3] + skin.PADDING, skin.GIVE_CONTENT_WIDTH, 1)
    line = cut(decode(files()[skin.PIECES_TEXTURE]), items(everything(), 'Ui2DAnimation')[divider.findtext('Animation')])
    assert line.size == line_box[2:] and set(pixels(line)) == {skin.ROW_DIVIDER_RGBA}
    # Give and Cancel a padding under it, two halves a padding apart filling the row.
    give, cancel = box(found['GVW_Give_Button']), box(found['GVW_Cancel_Button'])
    assert give[1] == cancel[1] == line_box[1] + line_box[3] + skin.BUTTON_ROW_GAP
    assert give[0] == skin.LEFT and give[0] + give[2] + skin.BUTTON_GAP == cancel[0]
    assert cancel[0] + cancel[2] == skin.GIVE_RIGHT and give[2] == cancel[2] == 78
    assert give[3] == cancel[3] == skin.TEXT_BUTTON_HEIGHT
    # The window's edge a padding under the buttons.
    assert box(window)[3] - (b + give[1] + give[3]) == skin.PADDING


def test_give_name_slots_and_buttons_take_what_the_game_puts_there():
    _, _, found = give_parts()
    # The game writes the NPC's name, in the text's color, on one line from the left.
    name = found['GVW_NPCName']
    assert name.findtext('Text') == '' and name.find('EQType') is None
    assert name.findtext('Font') == str(skin.TEXT_FONT) and rgb(name, 'TextColor') == skin.TEXT_RGB
    assert name.findtext('AlignLeft') == name.findtext('NoWrap') == 'true'
    # Empty slots are the hot bar's plain square, as in the bag and merchant windows.
    for n in range(4):
        assert found[f'GVW_MyItemSlot{n}'].findtext('Background') == 'TUI_HotButtonNormal'
    # Give and Cancel are the confirmation dialog's buttons, with no tooltips (the stock ones have none).
    for screen_id, button_name, _ in skin.GIVE_BUTTONS:
        check_confirmation_button(found[screen_id], button_name)
    assert [button_name for _, button_name, _ in skin.GIVE_BUTTONS] == ['Give', 'Cancel']


def test_give_coin_boxes_are_the_slots_wash_with_their_coin_named_over_them():
    # Platinum, gold, silver and copper, in the stock window's order (its coin decals), in reading order. The game
    # writes the amount as each box's text, centered, in font 3, and the coin's name is a label over the box (the
    # user's picks: over the stock coin pictures, then as big as the amount).
    root, window, found = give_parts()
    assert [caption for _, caption in skin.GIVE_COINS] == ['pp', 'gp', 'sp', 'cp']
    for n, (screen_id, caption) in enumerate(skin.GIVE_COINS):
        coin = found[screen_id]
        assert screen_id == f'GVW_MyMoney{n}'
        assert coin.findtext('Font') == str(skin.TEXT_FONT) and coin.findtext('Text') == ''
        assert rgb(coin, 'TextColor') == skin.TEXT_RGB
        assert coin.findtext('TooltipReference') == 'Drop coins here'  # the stock window's
        assert coin.findtext('Style_Checkbox') == 'false'
        assert [(e.tag, e.text) for e in coin.find('ButtonDrawTemplate')] == [
            (state, f'TUI_Coin{skin.BUTTON_ART[state]}') for state in skin.BUTTON_STATES]
        check_coin_caption(root, window, coin, caption)
    # Every box is the slots' plain wash in each look, solid like the slots, so a drop anywhere on one counts.
    anims = items(everything(), 'Ui2DAnimation')
    atlas = decode(files()[skin.PIECES_TEXTURE])
    for state in skin.BUTTON_LOOKS:
        image = cut(atlas, anims[f'TUI_Coin{state}'])
        plain = skin.solid(skin.labeled_button_art(skin.COIN_WIDTH, skin.COIN_HEIGHT, '', state))
        assert image.size == (skin.COIN_WIDTH, skin.COIN_HEIGHT)
        assert {a for *_, a in pixels(image)} == {255}, state
        assert all(image.getpixel((x, y)) == plain.rows[y][x]
                   for x in range(skin.COIN_WIDTH) for y in range(skin.COIN_HEIGHT)), state


def test_coin_names_are_level_with_the_amount_in_the_middle_of_the_box_clear_of_five_digits():
    # The game centers the amount's line in the box, so its digits' ink runs TEXT_INK_TOP down that line for 9px. The
    # names' lowercase ink (the x-height to the descenders) is as tall, LOWERCASE_DROP further down its line, so it runs
    # from the digits' top to their bottom (the user found them low on the amount's line): both in the box's middle,
    # within the pixel the game's centering of the amount's line leaves.
    digits = (skin.COIN_TEXT_TOP + skin.TEXT_INK_TOP, skin.COIN_TEXT_TOP + skin.TEXT_INK_TOP + 9)
    name = (skin.COIN_CAPTION_TOP + skin.TEXT_INK_TOP + skin.LOWERCASE_DROP,
            skin.COIN_CAPTION_TOP + skin.TEXT_INK_TOP + 9 + skin.LOWERCASE_DROP)
    assert skin.COIN_TEXT_TOP == (skin.COIN_HEIGHT - skin.TEXT_HEIGHT) // 2 and digits == name == (6.5, 15.5)
    assert abs((name[0] + name[1]) / 2 - skin.COIN_HEIGHT / 2) <= 1
    # Five digits of an amount (the stock placeholder's 60000), centered, start where the name's label ends, and its
    # line ends inside the box's edge.
    assert (skin.COIN_WIDTH - 5 * skin.DIGIT_WIDTH) / 2 >= skin.PADDING + skin.COIN_CAPTION_WIDTH
    assert 0 < skin.COIN_CAPTION_TOP and skin.COIN_CAPTION_TOP + skin.TEXT_HEIGHT < skin.COIN_HEIGHT


def trade_parts():
    root, window = screen(skin.TRADE_FILE)
    return root, window, {e.findtext('ScreenID') or e.get('item'): e for e in direct_pieces(root, window)}


def test_trade_window_keeps_every_control_the_client_looks_for():
    # eqgame.exe looks up the two names, the 16 slots (0 to 7 yours, 8 to 15 theirs), each side's four coin buttons,
    # Trade and Cancel, and nothing else: all of the stock window's controls, every one shown, in its order, over the
    # divider, each coin box followed by its name, and a divider of ours across over the buttons. With no title bar or
    # close box: it drags by its background, and Cancel closes it.
    root, window = check_inside_frame(skin.TRADE_FILE, skin.TRADE_WIDTH)
    assert window.get('item') == 'TradeWnd' and window.findtext('Text') == 'Trade'
    assert window.findtext('Style_Sizable') == window.findtext('Style_Closebox') == 'false'
    assert window.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    assert box(window)[2:] == (skin.TRADE_WIDTH, skin.TRADE_HEIGHT) == (181, 328)
    pieces = direct_pieces(root, window)

    def side(prefix, first):
        return [('Label', f'TRDW_{prefix}Name'), *(('InvSlot', f'TRDW_TradeSlot{first + n}') for n in range(8)),
                *(piece for n in range(4) for piece in (('Button', f'TRDW_{prefix}Money{n}'), ('Label', None)))]

    assert [(e.tag, e.findtext('ScreenID')) for e in pieces] == [
        ('Screen', None), *side('His', 8), *side('My', 0), ('StaticAnimation', None),
        ('Button', 'TRDW_Trade_Button'), ('Button', 'TRDW_Cancel_Button')]
    assert [number(e, 'EQType') for e in pieces if e.tag == 'InvSlot'] == [*range(3008, 3016), *range(3000, 3008)]
    assert all(box(e)[2:] != (0, 0) for e in pieces)


def test_trade_sides_are_theirs_then_yours_each_two_slots_across_under_its_name():
    _, _, found = trade_parts()
    # The stock window's arrangement and numbering: theirs on the left, yours on the right, each side's slots down its
    # first column and then its second, on the hot bar's squares a padding apart. Empty ones are the plain square, as in
    # the bag, merchant and give windows.
    assert [(prefix, first) for prefix, _, first in skin.TRADE_SIDES] == [('His', 8), ('My', 0)]
    assert skin.TRADE_SIDES[0][1] < skin.TRADE_SIDES[1][1]
    for prefix, x, first in skin.TRADE_SIDES:
        for n in range(8):
            slot = found[f'TRDW_TradeSlot{first + n}']
            assert box(slot) == (x + n // 4 * skin.HOT_PITCH, skin.TRADE_SLOTS_TOP + n % 4 * skin.HOT_PITCH,
                                 skin.HOT_SIZE, skin.HOT_SIZE)
            assert slot.findtext('Background') == 'TUI_HotButtonNormal'
        # The game writes each name, centered over its side on one line, in the text's font and color.
        name = found[f'TRDW_{prefix}Name']
        assert box(name) == (x, skin.TRADE_NAME_TOP, skin.TRADE_SIDE_WIDTH, skin.TEXT_HEIGHT)
        assert name.findtext('Text') == '' and name.find('EQType') is None
        assert name.findtext('Font') == str(skin.TEXT_FONT) and rgb(name, 'TextColor') == skin.TEXT_RGB
        assert name.findtext('AlignCenter') == name.findtext('NoWrap') == 'true'
    # Trade and Cancel are the confirmation dialog's buttons, with no tooltips (the stock ones have none).
    for screen_id, button_name, _ in skin.TRADE_BUTTONS:
        check_confirmation_button(found[screen_id], button_name)
    assert [button_name for _, button_name, _ in skin.TRADE_BUTTONS] == ['Trade', 'Cancel']


def test_trade_window_follows_the_spacing_standard():
    _, window, found = trade_parts()
    b = skin.BORDER
    (_, his, _), (_, mine, _) = skin.TRADE_SIDES
    # The names' line at the inside's top: their ink starts 7.5px under the window's edge, the closest the frame allows
    # (a label placed into it isn't drawn). An agreed exception: the user picked font 3 for the names over font 2,
    # whose capitals would have started 6px under it.
    assert b + skin.TRADE_NAME_TOP + skin.TEXT_INK_TOP == 7.5
    # Across: the sides from the window's padding to its padding, the divider between them a padding from each.
    divider = box(found['TUI_TRDW_Divider'])
    assert his == skin.LEFT and b + skin.LEFT == skin.PADDING
    assert divider[0] == his + skin.TRADE_SIDE_WIDTH + skin.PADDING and divider[2] == skin.DIVIDER_HEIGHT == 1
    assert mine == divider[0] + divider[2] + skin.PADDING
    assert mine + skin.TRADE_SIDE_WIDTH == skin.TRADE_RIGHT and skin.TRADE_WIDTH - 2 * b - skin.TRADE_RIGHT == skin.LEFT
    # Down each side: the slots a padding under the names' capitals and digits, the coins a padding under the slots and
    # a padding apart, each as wide as the side's two columns of slots.
    for prefix, x, first in skin.TRADE_SIDES:
        top = box(found[f'TRDW_TradeSlot{first}'])[1]
        assert top == skin.TRADE_NAME_TOP + skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT + skin.PADDING
        last = box(found[f'TRDW_TradeSlot{first + 7}'])
        assert last[0] + last[2] == x + skin.TRADE_SIDE_WIDTH
        coins = [box(found[f'TRDW_{prefix}Money{n}']) for n in range(4)]
        assert coins[0][1] == last[1] + last[3] + skin.BUTTON_ROW_GAP
        for above, coin in zip(coins, coins[1:]):
            assert coin[1] == above[1] + above[3] + skin.BUTTON_ROW_GAP
        assert all(c[0] == x and c[2:] == (skin.TRADE_SIDE_WIDTH, skin.TEXT_BUTTON_HEIGHT) for c in coins)
    bottom = coins[-1][1] + coins[-1][3]
    # The divider from the window's padding at the top down to the coins' bottom.
    assert b + divider[1] == skin.PADDING and divider[1] + divider[3] == bottom
    # The row divider across the content row a padding under the coins and the divider between the sides (the user's
    # request), as in the give window.
    row_divider = found['TUI_TRDW_RowDivider']
    line_box = box(row_divider)
    assert line_box == (skin.LEFT, bottom + skin.PADDING, skin.TRADE_CONTENT_WIDTH, skin.DIVIDER_HEIGHT)
    line = cut(decode(files()[skin.PIECES_TEXTURE]),
               items(everything(), 'Ui2DAnimation')[row_divider.findtext('Animation')])
    assert line.size == line_box[2:] and set(pixels(line)) == {skin.ROW_DIVIDER_RGBA}
    # Trade and Cancel fill the row a padding under it, a padding apart, and the window's edge is a padding under them.
    trade, cancel = box(found['TRDW_Trade_Button']), box(found['TRDW_Cancel_Button'])
    assert trade[1] == cancel[1] == line_box[1] + line_box[3] + skin.BUTTON_ROW_GAP
    assert trade[0] == skin.LEFT and trade[0] + trade[2] + skin.BUTTON_GAP == cancel[0]
    assert cancel[0] + cancel[2] == skin.TRADE_RIGHT and cancel[2] - trade[2] in (0, 1)
    assert trade[3] == cancel[3] == skin.TEXT_BUTTON_HEIGHT
    assert box(window)[3] - (b + trade[1] + trade[3]) == skin.PADDING


def test_trade_divider_is_the_row_divider_standing_up():
    # A child window 1px wide drawing only its background, in the row divider's color: a piece that tall doesn't fit in
    # the atlas.
    _, _, found = trade_parts()
    divider = found['TUI_TRDW_Divider']
    assert divider.tag == 'Screen' and divider.find('ScreenID') is None and divider.find('Pieces') is None
    assert divider.findtext('DrawTemplate') == skin.DIVIDER_TEMPLATE
    assert divider.findtext('Style_Transparent') == divider.findtext('Style_Border') == 'false'
    template = items(parse(skin.ANIMATIONS_FILE), 'WindowDrawTemplate')[skin.DIVIDER_TEMPLATE]
    assert template.findtext('Background') == skin.DIVIDER_TEXTURE
    assert {template.findtext(f'Border/{side}') for side in skin.BORDER_PIECES} == {'TUI_Clear'}
    assert set(pixels(decode(files()[skin.DIVIDER_TEXTURE]))) == {skin.ROW_DIVIDER_RGBA}


def test_trade_coin_boxes_are_the_give_windows_and_only_yours_take_coins():
    # Platinum, gold, silver and copper down each side, in the give window's boxes with their coins' names over them (see
    # COIN_CAPTIONS): the game writes each amount, centered, in font 3. Yours light up under the pointer and say coins go
    # there, as the give window's do; theirs take nothing, so they keep their resting look and have no tooltip.
    root, window, found = trade_parts()
    give = give_parts()[2]
    assert skin.COIN_CAPTIONS == ('pp', 'gp', 'sp', 'cp')
    for prefix, _, _ in skin.TRADE_SIDES:
        for n, caption in enumerate(skin.COIN_CAPTIONS):
            coin, given = found[f'TRDW_{prefix}Money{n}'], give[f'GVW_MyMoney{n}']
            assert coin.findtext('Font') == str(skin.TEXT_FONT) and coin.findtext('Text') == ''
            assert rgb(coin, 'TextColor') == skin.TEXT_RGB and coin.findtext('Style_Checkbox') == 'false'
            assert box(coin)[2:] == box(given)[2:] == (skin.COIN_WIDTH, skin.COIN_HEIGHT)
            art = [(e.tag, e.text) for e in coin.find('ButtonDrawTemplate')]
            if prefix == 'My':
                assert art == [(e.tag, e.text) for e in given.find('ButtonDrawTemplate')]
                assert coin.findtext('TooltipReference') == given.findtext('TooltipReference') == 'Drop coins here'
            else:
                assert art == [(state, 'TUI_CoinNormal') for state in skin.BUTTON_STATES]
                assert coin.find('TooltipReference') is None
            check_coin_caption(root, window, coin, caption)


def loot_parts():
    root, window = screen(skin.LOOT_FILE)
    return root, window, {e.findtext('ScreenID'): e for e in direct_pieces(root, window)}


def test_loot_window_keeps_every_control_the_client_and_zeal_look_for():
    # eqgame.exe looks up the corpse's name, the slots' panel and its 30 slots, and Done; Zeal looks up Link All and
    # Loot All. Every one is shown, in reading order. With no title bar or close box: it drags by its background, and
    # Done closes it.
    root, window = check_inside_frame(skin.LOOT_FILE, skin.LOOT_WIDTH)
    assert window.get('item') == 'LootWnd' and window.findtext('Text') == 'Loot'
    assert window.findtext('Style_Sizable') == window.findtext('Style_Closebox') == 'false'
    assert window.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    assert box(window)[2:] == (skin.LOOT_WIDTH, skin.LOOT_HEIGHT) == (258, 259)
    pieces = direct_pieces(root, window)
    assert [(e.tag, e.findtext('ScreenID')) for e in pieces] == [
        ('Label', 'LW_CorpseName'), ('Screen', 'LootInvWnd'), ('Button', 'LinkAllButton'),
        ('Button', 'LootAllButton'), ('Button', 'DoneButton')]
    # The 30 slots are the pieces of the client's panel for them, not the window's, each its own EQType.
    slots = direct_pieces(root, pieces[1])
    assert {s.tag for s in slots} == {'InvSlot'}
    assert [s.findtext('ScreenID') for s in slots] == [f'LW_LootSlot{n}' for n in range(30)]
    assert [number(s, 'EQType') for s in slots] == list(range(5000, 5030))
    assert all(box(e)[2:] != (0, 0) for e in pieces + slots)


def test_loot_slots_are_all_30_six_across_on_the_hot_bars_squares():
    root, _, found = loot_parts()
    panel = found['LootInvWnd']
    # All at once, nothing to scroll (the user's pick): the panel is exactly the grid, see-through on the window's
    # panel, placed by Location and Size like the merchant's.
    assert (skin.LOOT_COLUMNS, skin.LOOT_ROWS) == (6, 5)
    assert box(panel) == (skin.LEFT, skin.LOOT_SLOTS_TOP, skin.LOOT_CONTENT_WIDTH, skin.LOOT_GRID_HEIGHT)
    assert panel.findtext('Style_VScroll') == 'false' and panel.findtext('Style_Transparent') == 'true'
    assert panel.findtext('Style_Border') == 'false' and panel.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    assert panel.find('AutoStretch') is None
    # The hot bar's 36px squares, a padding apart, left to right then down; empty ones the plain square.
    slots = direct_pieces(root, panel)
    for n, slot in enumerate(slots):
        assert box(slot) == (n % 6 * skin.HOT_PITCH, n // 6 * skin.HOT_PITCH, skin.HOT_SIZE, skin.HOT_SIZE)
        assert slot.findtext('Background') == 'TUI_HotButtonNormal'
    x, y, width, height = box(slots[-1])
    assert (x + width, y + height) == box(panel)[2:]


def test_loot_window_follows_the_spacing_standard():
    _, window, found = loot_parts()
    b = skin.BORDER
    # The name's line at the inside's top, across the content row: its ink starts 7.5px under the window's edge, the
    # closest the frame allows (a label placed into it isn't drawn), as in the give and trade windows.
    name = box(found['LW_CorpseName'])
    assert name == (skin.LEFT, 0, skin.LOOT_CONTENT_WIDTH, skin.TEXT_HEIGHT)
    assert b + name[1] + skin.TEXT_INK_TOP == 7.5
    # The slots a padding under the name's capitals and digits, filling the row from the window's padding to its
    # padding.
    panel = box(found['LootInvWnd'])
    assert panel[1] == name[1] + skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT + skin.PADDING
    assert b + panel[0] == skin.PADDING and panel[0] + panel[2] == skin.LOOT_RIGHT
    assert skin.LOOT_WIDTH - 2 * b - skin.LOOT_RIGHT == skin.LEFT
    # Link All, Loot All and Done fill the row a padding under the slots, a padding apart and equally wide, and the
    # window's edge is a padding under them.
    buttons = [box(found[screen_id]) for screen_id, _, _ in skin.LOOT_BUTTONS]
    assert {button[1] for button in buttons} == {panel[1] + panel[3] + skin.BUTTON_ROW_GAP}
    assert buttons[0][0] == skin.LEFT and buttons[-1][0] + buttons[-1][2] == skin.LOOT_RIGHT
    for left, right in zip(buttons, buttons[1:]):
        assert left[0] + left[2] + skin.BUTTON_GAP == right[0]
    assert {button[2:] for button in buttons} == {(78, skin.TEXT_BUTTON_HEIGHT)}
    assert box(window)[3] - (b + buttons[0][1] + buttons[0][3]) == skin.PADDING


def test_loot_name_and_buttons_take_what_the_game_and_zeal_put_there():
    _, _, found = loot_parts()
    # The game writes the corpse's name, in the text's color, on one line from the left, as the give window's NPC.
    name = found['LW_CorpseName']
    assert name.findtext('Text') == '' and name.find('EQType') is None
    assert name.findtext('Font') == str(skin.TEXT_FONT) and rgb(name, 'TextColor') == skin.TEXT_RGB
    assert name.findtext('AlignLeft') == name.findtext('NoWrap') == 'true'
    # duxaUI's three buttons in its order, the confirmation dialog's kind, with no tooltips (neither the stock Done nor
    # duxaUI's have one).
    for screen_id, button_name, _ in skin.LOOT_BUTTONS:
        check_confirmation_button(found[screen_id], button_name)
    assert [(screen_id, button_name) for screen_id, button_name, _ in skin.LOOT_BUTTONS] == [
        ('LinkAllButton', 'Link All'), ('LootAllButton', 'Loot All'), ('DoneButton', 'Done')]


def bank_parts():
    root, window = screen(skin.BANK_FILE)
    return root, window, {e.findtext('ScreenID') or e.get('item'): e for e in direct_pieces(root, window)}


def test_bank_window_keeps_every_control_the_client_and_zeal_look_for():
    # eqgame.exe looks up the banker's name, the bank's slots, its four coin buttons and Done; Zeal looks up Change. The
    # stock window's shared slots and their caption stay too: the slots work by their EQType. Every one is shown, in the
    # stock window's order with duxaUI's Change last, over the divider, each coin box followed by its name. With no
    # title bar or close box: it drags by its background, and Done closes it.
    root, window = check_inside_frame(skin.BANK_FILE, skin.BANK_WIDTH)
    assert window.get('item') == 'BankWnd' and window.findtext('Text') == 'Bank'
    assert window.findtext('Style_Sizable') == window.findtext('Style_Closebox') == 'false'
    assert window.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    assert box(window)[2:] == (skin.BANK_WIDTH, skin.BANK_HEIGHT) == (349, 285)
    pieces = direct_pieces(root, window)
    assert [(e.tag, e.findtext('ScreenID')) for e in pieces] == [
        ('Screen', None), ('Label', 'BW_BankerName'), ('Label', 'BW_SharedBankLabel'),
        *(('InvSlot', f'BW_SharedBankSlot{n}') for n in range(10)), *(('InvSlot', f'BW_BankSlot{n}') for n in range(30)),
        *(piece for n in range(4) for piece in (('Button', f'BW_Money{n}'), ('Label', None))),
        ('Button', 'DoneButton'), ('Button', 'ChangeButton')]
    assert [number(e, 'EQType') for e in pieces if e.tag == 'InvSlot'] == [*range(2500, 2510), *range(2000, 2030)]
    assert all(box(e)[2:] != (0, 0) for e in pieces)


def test_bank_slots_keep_the_stock_order_down_each_column():
    # The stock window's numbering: each grid five rows tall, down its first column and then the next, so an item sits
    # where players saw it there. The shared bank's two columns on the left, the bank's six on the right, on the hot
    # bar's squares a padding apart; empty ones are the plain square, as in the loot window.
    _, _, found = bank_parts()
    assert (skin.SHARED_COLUMNS, skin.BANK_COLUMNS, skin.BANK_ROWS) == (2, 6, 5)
    for prefix, x, slots in (('SharedBank', skin.LEFT, 10), ('Bank', skin.BANK_X, 30)):
        for n in range(slots):
            slot = found[f'BW_{prefix}Slot{n}']
            assert box(slot) == (x + n // 5 * skin.HOT_PITCH, skin.BANK_SLOTS_TOP + n % 5 * skin.HOT_PITCH,
                                 skin.HOT_SIZE, skin.HOT_SIZE)
            assert slot.findtext('Background') == 'TUI_HotButtonNormal'


def test_bank_window_follows_the_spacing_standard():
    _, window, found = bank_parts()
    b = skin.BORDER
    # The caption's and the name's line at the inside's top: their ink starts 7.5px under the window's edge, as in the
    # trade window. The slots a padding under their capitals' ink.
    caption, name = box(found['BW_SharedBankLabel']), box(found['BW_BankerName'])
    assert caption == (skin.LEFT, 0, skin.SHARED_WIDTH, skin.TEXT_HEIGHT)
    assert name == (skin.BANK_X, 0, skin.BANK_CONTENT_WIDTH, skin.TEXT_HEIGHT)
    assert b + skin.BANK_NAME_TOP + skin.TEXT_INK_TOP == 7.5
    top = skin.BANK_NAME_TOP + skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT + skin.PADDING
    assert box(found['BW_SharedBankSlot0'])[1] == box(found['BW_BankSlot0'])[1] == top
    # Across: the shared slots from the window's padding, the divider a padding from them and from the bank's slots,
    # and those to the window's padding.
    divider = box(found['TUI_BW_Divider'])
    shared_right = box(found['BW_SharedBankSlot9'])
    assert b + skin.LEFT == skin.PADDING and shared_right[0] + shared_right[2] == skin.LEFT + skin.SHARED_WIDTH
    assert divider[0] == skin.LEFT + skin.SHARED_WIDTH + skin.PADDING and divider[2] == skin.DIVIDER_HEIGHT == 1
    assert skin.BANK_X == divider[0] + divider[2] + skin.PADDING
    last = box(found['BW_BankSlot29'])
    assert last[0] + last[2] == skin.BANK_RIGHT and skin.BANK_WIDTH - 2 * b - skin.BANK_RIGHT == skin.LEFT
    # Down: the band a padding under the slots, two rows a padding apart. Change over Done at the shared column's width;
    # the coins two across a padding apart, platinum to copper in reading order (pp gp, then sp cp, as in the give
    # window), filling the bank's width.
    band = last[1] + last[3] + skin.BUTTON_ROW_GAP
    change, done = box(found['ChangeButton']), box(found['DoneButton'])
    assert change == (skin.LEFT, band, skin.SHARED_WIDTH, skin.TEXT_BUTTON_HEIGHT) and skin.SHARED_WIDTH == 78
    assert done == (skin.LEFT, change[1] + change[3] + skin.BUTTON_ROW_GAP, skin.SHARED_WIDTH, skin.TEXT_BUTTON_HEIGHT)
    coins = [box(found[f'BW_Money{n}']) for n in range(4)]
    pitch = skin.BANK_COIN_WIDTH + skin.BUTTON_GAP, skin.COIN_HEIGHT + skin.BUTTON_ROW_GAP
    assert coins == [(skin.BANK_X + n % 2 * pitch[0], band + n // 2 * pitch[1], skin.BANK_COIN_WIDTH,
                      skin.TEXT_BUTTON_HEIGHT) for n in range(4)]
    assert coins[1][0] + coins[1][2] == skin.BANK_RIGHT and coins[3][1] == done[1]
    # The divider from the window's padding at the top down to the band's bottom, and the window's edge a padding under
    # the band.
    bottom = done[1] + done[3]
    assert b + divider[1] == skin.PADDING and divider[1] + divider[3] == bottom
    assert box(window)[3] - (b + bottom) == skin.PADDING


def test_bank_names_and_buttons_take_what_the_game_and_zeal_put_there():
    _, _, found = bank_parts()
    # The game writes the banker's name, in the text's color, on one line from the left, as the give window's NPC.
    name = found['BW_BankerName']
    assert name.findtext('Text') == '' and name.find('EQType') is None
    assert name.findtext('Font') == str(skin.TEXT_FONT) and rgb(name, 'TextColor') == skin.TEXT_RGB
    assert name.findtext('AlignLeft') == name.findtext('NoWrap') == 'true'
    # Nothing writes the stock caption: it's ours, in the same font and color, and fits the shared column (71px of ink
    # in font 3, which tools/preview.py checks by drawing it).
    caption = found['BW_SharedBankLabel']
    assert caption.findtext('Text') == skin.SHARED_CAPTION == 'Shared Bank' and caption.find('EQType') is None
    assert caption.findtext('Font') == str(skin.TEXT_FONT) and rgb(caption, 'TextColor') == skin.TEXT_RGB
    assert caption.findtext('AlignLeft') == caption.findtext('NoWrap') == 'true'
    # Change and Done are the confirmation dialog's buttons, with no tooltips (neither duxaUI's nor the stock Done has
    # one), in duxaUI's order.
    for screen_id, button_name, _ in skin.BANK_BUTTONS:
        check_confirmation_button(found[screen_id], button_name)
    assert [(screen_id, button_name) for screen_id, button_name, _ in skin.BANK_BUTTONS] == [
        ('DoneButton', 'Done'), ('ChangeButton', 'Change')]


def test_bank_coin_boxes_are_the_give_windows_wider_with_the_stock_tooltips():
    # Platinum, gold, silver and copper, in the stock window's order (its coin decals), each with its coin's name over
    # it (see COIN_CAPTIONS): the game writes the amount, centered, in font 3. They take coins and give them back, so
    # they light up under the pointer like the give window's, and keep the stock window's tooltips.
    root, window, found = bank_parts()
    coins = ('Platinum', 'Gold', 'Silver', 'Copper')
    assert [(screen_id, caption) for screen_id, caption, _ in skin.BANK_COINS] == [
        (f'BW_Money{n}', caption) for n, caption in enumerate(skin.COIN_CAPTIONS)]
    for (screen_id, caption, _), coin_name in zip(skin.BANK_COINS, coins):
        coin = found[screen_id]
        assert coin.findtext('Font') == str(skin.TEXT_FONT) and coin.findtext('Text') == ''
        assert rgb(coin, 'TextColor') == skin.TEXT_RGB and coin.findtext('Style_Checkbox') == 'false'
        assert coin.findtext('TooltipReference') == f'Drop coins here or click to pick up {coin_name}'
        assert [(e.tag, e.text) for e in coin.find('ButtonDrawTemplate')] == [
            (state, f'TUI_BankCoin{skin.BUTTON_ART[state]}') for state in skin.BUTTON_STATES]
        check_coin_caption(root, window, coin, caption)
    # Wider than the give window's so seven digits of platinum, centered, start where the name's label ends.
    assert skin.BANK_COIN_WIDTH == 120 > skin.COIN_WIDTH
    assert (skin.BANK_COIN_WIDTH - 7 * skin.DIGIT_WIDTH) / 2 >= skin.PADDING + skin.COIN_CAPTION_WIDTH
    # Every box is the slots' plain wash in each look at its own width, solid, so a drop anywhere on one counts.
    anims = items(everything(), 'Ui2DAnimation')
    atlas = decode(files()[skin.PIECES_TEXTURE])
    for state in skin.BUTTON_LOOKS:
        image = cut(atlas, anims[f'TUI_BankCoin{state}'])
        plain = skin.solid(skin.labeled_button_art(skin.BANK_COIN_WIDTH, skin.COIN_HEIGHT, '', state))
        assert image.size == (skin.BANK_COIN_WIDTH, skin.COIN_HEIGHT)
        assert {a for *_, a in pixels(image)} == {255}, state
        assert all(image.getpixel((x, y)) == plain.rows[y][x]
                   for x in range(skin.BANK_COIN_WIDTH) for y in range(skin.COIN_HEIGHT)), state


# The skills window

def skills_parts():
    root, window = screen(skin.SKILLS_FILE)
    return root, window, {e.findtext('ScreenID'): e for e in direct_pieces(root, window)}


def test_skills_window_keeps_every_control_the_stock_one_has():
    # eqgame.exe looks up only the list; Done is the stock window's other control. A fixed size with no title bar or
    # close box (the user's pick), so it drags by its background and Done closes it.
    root, window = check_inside_frame(skin.SKILLS_FILE, skin.SKILLS_WIDTH)
    assert window.get('item') == 'SkillsWindow' and window.findtext('Text') == 'Skills'
    assert window.findtext('Style_Sizable') == window.findtext('Style_Closebox') == 'false'
    assert window.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    assert box(window)[2:] == (skin.SKILLS_WIDTH, skin.SKILLS_HEIGHT) == (195, 390)
    assert [(e.tag, e.findtext('ScreenID')) for e in direct_pieces(root, window)] == [
        ('Listbox', 'SkillList'), ('Button', 'DoneButton')]


def test_skills_list_shows_name_and_value_with_the_rank_hidden():
    _, _, found = skills_parts()
    listbox = found['SkillList']
    columns = listbox.findall('Columns')
    # The client's three columns in its order, since Zeal sorts by the first and third headings; the rank column has
    # no width and no heading (the user's pick).
    assert [c.findtext('Heading') for c in columns] == ['Skill', '', 'Value']
    widths = [number(c, 'Width') for c in columns]
    assert columns[1].find('Header') is None
    assert all(c.findtext('Header') == skin.LIST_HEADER for c in (columns[0], columns[2]))
    # Each as wide as its widest text in font 3 (Arial 12px) and a padding: "Percussion Instruments" and "Value".
    assert widths == [127 + skin.PADDING, 0, 32 + skin.PADDING]
    # The columns and the scrollbar fill the list, which spans the window between its paddings, 24 rows tall under
    # its heading row.
    x, y, width, height = box(listbox)
    assert sum(widths) + skin.SCROLL_WIDTH == width == skin.SKILLS_WIDTH - 2 * skin.PADDING
    assert height == skin.RAID_HEADER_HEIGHT + 24 * skin.TEXT_HEIGHT and skin.SKILLS_ROWS == 24
    # Straight on the window's panel, only the slim scrollbar drawn, in the windows' font, with no tooltip (the stock
    # list has none).
    assert listbox.findtext('DrawTemplate') == skin.EDIT_TEMPLATE
    assert listbox.findtext('Style_VScroll') == 'true' and listbox.findtext('Style_Border') == 'false'
    assert listbox.findtext('Font') == str(skin.TEXT_FONT) and rgb(listbox, 'TextColor') == skin.TEXT_RGB
    assert listbox.find('TooltipReference') is None


def test_skills_window_follows_the_spacing_standard():
    _, window, found = skills_parts()
    skills, done = box(found['SkillList']), box(found['DoneButton'])
    # The heading strip a padding from the window's edge, across and down.
    assert skills[:2] == (skin.LEFT, skin.LEFT) and skin.BORDER + skin.LEFT == skin.PADDING
    # Done a padding under the list and as wide, and the window's edge a padding under it.
    assert done[1] - (skills[1] + skills[3]) == skin.BUTTON_ROW_GAP == skin.PADDING
    assert (done[0], done[2], done[3]) == (skin.LEFT, skills[2], skin.TEXT_BUTTON_HEIGHT)
    assert box(window)[3] == 2 * skin.BORDER + done[1] + done[3] + skin.BOTTOM_GAP
    assert skin.BORDER + skin.BOTTOM_GAP == skin.PADDING


def test_skills_done_is_the_confirmation_dialogs_kind_of_button():
    # No tooltip: the stock Done has none.
    _, _, found = skills_parts()
    check_confirmation_button(found['DoneButton'], 'Done')


def compass_parts():
    root, window = screen(skin.COMPASS_FILE)
    return root, window, {e.findtext('ScreenID'): e for e in direct_pieces(root, window)}


def compass_art(name):
    """One of the compass's pieces of art, cut from the atlas."""
    return cut(decode(files()[skin.PIECES_TEXTURE]), items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')[f'TUI_{name}'])


def stock_compass():
    """default's compass window file, and its strip's and overlay's art, or a skip without an EverQuest folder."""
    for folder in EQ_DIRS:
        default = Path(folder) / 'uifiles' / 'default'
        if folder and (default / skin.COMPASS_FILE).is_file():
            animations = (default / skin.ANIMATIONS_FILE).read_text(encoding='latin-1')
            art = []
            for name in ('A_CompassStrip', 'A_CompassOverlay'):
                anim = ET.fromstring(re.search(rf'<Ui2DAnimation item\s*=\s*"{name}"\s*>.*?</Ui2DAnimation>',
                                               animations, flags=re.S).group(0))
                art.append(cut(Image.open(default / anim.findtext('Frames/Texture')).convert('RGBA'), anim))
            return ET.fromstring((default / skin.COMPASS_FILE).read_bytes()), *art
    pytest.skip('no EverQuest folder with uifiles/default here')


def test_compass_window_keeps_every_control_the_client_looks_for():
    # The client looks up the two strips it slides and the overlay over them, still pictures drawn in the stock order,
    # the overlay last. With no title bar, close box or name, as in the stock window: nothing in it takes a click, so it
    # drags by any part.
    root, window = check_inside_frame(skin.COMPASS_FILE, skin.COMPASS_WIDTH)
    assert window.get('item') == 'CompassWindow' and window.find('Text') is None
    assert window.findtext('Style_Sizable') == window.findtext('Style_Closebox') == 'false'
    assert window.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    assert box(window)[2:] == (skin.COMPASS_WIDTH, skin.COMPASS_HEIGHT) == (106, 30)
    pieces = direct_pieces(root, window)
    assert [(e.tag, e.findtext('ScreenID')) for e in pieces] == [
        ('StaticAnimation', 'CompassStrip1'), ('StaticAnimation', 'CompassStrip2'), ('StaticAnimation', 'CompassOverlay')]
    # Both strips are the one strip, as wide as the game's, at the inside's left as in the stock file; the overlay covers
    # the inside. Each is its art's size.
    inside = (skin.COMPASS_INSIDE_WIDTH, skin.COMPASS_INSIDE_HEIGHT)
    strip = (0, 0, skin.COMPASS_STRIP_WIDTH, inside[1])
    assert [(box(e), e.findtext('Animation')) for e in pieces] == [
        (strip, 'TUI_CompassStrip'), (strip, 'TUI_CompassStrip'), ((0, 0, *inside), 'TUI_CompassOverlay')]
    assert compass_art('CompassStrip').size == strip[2:] and compass_art('CompassOverlay').size == inside


def test_compass_marks_sit_where_the_stock_strip_has_them():
    # The game lines the heading up with the pointer by where the stock art puts each mark, so ours are where the stock
    # strip has them: a tick every 10°, the wider ones under E, S, W and N, across the strip's width; the pointer at
    # the stock one's column (the tip of the notch hanging from the overlay's top edge); and the window the stock one's
    # width, so its inside is too.
    window_file, strip, overlay = stock_compass()
    stock = {e.findtext('ScreenID'): e for e in window_file if e.tag == 'StaticAnimation'}
    assert set(stock) == {*skin.COMPASS_STRIPS, 'CompassOverlay'}
    assert {box(stock[screen_id])[2] for screen_id in skin.COMPASS_STRIPS} == {strip.width} == {skin.COMPASS_STRIP_WIDTH}
    assert box(window_file[-1])[2] == skin.COMPASS_WIDTH
    bottom = strip.height - 1
    paper = strip.getpixel((0, bottom))
    runs = []
    for x in range(strip.width):
        if sum(abs(a - b) for a, b in zip(strip.getpixel((x, bottom))[:3], paper[:3])) > 60:
            if runs and runs[-1][1] == x - 1:
                runs[-1][1] = x
            else:
                runs.append([x, x])
    assert [(a + b) / 2 for a, b in runs] == list(range(skin.COMPASS_NORTH_X % skin.COMPASS_TICK_STEP,
                                                       skin.COMPASS_STRIP_WIDTH, skin.COMPASS_TICK_STEP))
    cardinals = {int(skin.compass_mark_center(degrees)) for label, degrees, _ in skin.COMPASS_MARKS if len(label) == 1}
    assert {(a + b) // 2 for a, b in runs if b > a} == cardinals == {11, 56, 101, 146}
    x, y = skin.COMPASS_POINTER_X, 0
    while overlay.getpixel((x, y + 1))[3]:
        y += 1
    left, right = x, x
    while overlay.getpixel((left - 1, y))[3]:
        left -= 1
    while overlay.getpixel((right + 1, y))[3]:
        right += 1
    assert y > skin.BORDER and (left, right) == (x - 1, x + 1)


def test_compass_strip_is_a_tick_every_10_degrees_and_eight_labels_over_their_headings():
    strip = compass_art('CompassStrip')
    drawn = {(x, y): strip.getpixel((x, y)) for x in range(strip.width) for y in range(strip.height)
             if strip.getpixel((x, y))[3]}
    # Each heading half a pixel a degree from north's column (a column's middle is its index + 0.5): N, E, S and W on a
    # column's middle, the others between two columns.
    assert [(label, skin.compass_mark_center(degrees)) for label, degrees, _ in skin.COMPASS_MARKS] == [
        ('N', 146.5), ('NE', 169), ('E', 11.5), ('SE', 34), ('S', 56.5), ('SW', 79), ('W', 101.5), ('NW', 124)]
    # A faint tick every 10° along the bottom of the tick row, the bars' track color, and a taller one in the text's
    # color under N, E, S and W; they stay 5px apart across the strip's ends, where the game's two copies meet.
    cardinals = {11, 56, 101, 146}
    top, bottom = skin.COMPASS_TICKS_TOP, skin.COMPASS_TICKS_TOP + skin.COMPASS_TICKS_HEIGHT
    expected = {}
    for x in range(1, skin.COMPASS_STRIP_WIDTH, 5):
        for y in range(top if x in cardinals else bottom - skin.COMPASS_TICK_HEIGHT, bottom):
            expected[x, y] = skin.snapped((*skin.TEXT_RGB, 255)) if x in cardinals else skin.EDGE_FADED
    assert {spot: p for spot, p in drawn.items() if spot[1] >= top} == expected
    assert (skin.COMPASS_TICK_HEIGHT, skin.COMPASS_TICKS_HEIGHT) == (2, 5)
    columns = sorted({x for x, _ in expected})
    assert columns[0] + skin.COMPASS_STRIP_WIDTH - columns[-1] == 5
    # Each label in our lettering, centered exactly on its heading, its ink along the letters' row: N in the casting
    # window's soft red, E, S and W in the text's color, the others in the overlays' grey. Nothing else is drawn.
    colors = {label: rgb for label, _, rgb in skin.COMPASS_MARKS}
    assert colors['N'] == skin.SPELL_RGB and colors['E'] == colors['S'] == colors['W'] == skin.TEXT_RGB
    assert {colors[label] for label in ('NE', 'SE', 'SW', 'NW')} == {skin.PET_RGB}
    expected = {}
    for label, degrees, rgb in skin.COMPASS_MARKS:
        width, ink = skin.lettering(label)
        assert width == (5 if len(label) == 1 else 12)
        left = skin.compass_mark_center(degrees) - width / 2
        assert left == int(left) and 0 <= left and left + width <= skin.COMPASS_STRIP_WIDTH
        for x, y in ink:
            expected[int(left) + x, skin.COMPASS_LETTERS_TOP + y] = skin.snapped((*rgb, 255))
    assert {spot: p for spot, p in drawn.items() if spot[1] < top} == expected


def test_compass_overlay_is_a_red_pointer_with_the_strip_faded_out_at_the_sides():
    overlay = compass_art('CompassOverlay')
    width, height = overlay.size
    # The pointer: a 1px line in north's soft red through the tick row, at the stock pointer's column.
    pointer = [overlay.getpixel((skin.COMPASS_POINTER_X, y)) for y in range(height)]
    rows = range(skin.COMPASS_TICKS_TOP, skin.COMPASS_TICKS_TOP + skin.COMPASS_TICKS_HEIGHT)
    assert [y for y, p in enumerate(pointer) if p[3]] == list(rows)
    assert {pointer[y] for y in rows} == {skin.snapped((*skin.COMPASS_NORTH_RGB, 255))}
    # Everything else the panel's color, the same all the way down each column: opaque within the window's padding,
    # fading to clear over COMPASS_FADE more, the same on both sides, and clear between.
    fades = []
    for x in range(width):
        column = {overlay.getpixel((x, y)) for y in range(height) if (x, y) not in {(skin.COMPASS_POINTER_X, y) for y in rows}}
        assert len(column) == 1 and next(iter(column))[:3] == skin.PANEL_RGBA[:3], x
        fades.append(next(iter(column))[3])
    margin = skin.LEFT + skin.COMPASS_FADE
    assert fades == fades[::-1]
    assert fades[:skin.LEFT] == [255] * skin.LEFT and set(fades[margin:width - margin]) == {0}
    assert all(a > b for a, b in zip(fades[skin.LEFT - 1:margin], fades[skin.LEFT:margin + 1]))


def test_compass_window_follows_the_spacing_standard():
    b = skin.BORDER
    _, window, _ = compass_parts()
    # Down: our lettering's ink starts at its top, a padding under the window's edge; the tick row (the ticks and the
    # pointer) a padding under the letters' ink; the window's edge a padding under it.
    strip = compass_art('CompassStrip')
    inked = [y for y in range(strip.height) if any(strip.getpixel((x, y))[3] for x in range(strip.width))]
    letters = [y for y in inked if y < skin.COMPASS_TICKS_TOP]
    ticks = [y for y in inked if y >= skin.COMPASS_TICKS_TOP]
    assert b + letters[0] == skin.PADDING and len(letters) == skin.LABEL_HEIGHT
    assert ticks[0] - (letters[-1] + 1) == skin.PADDING
    assert box(window)[3] - (b + ticks[-1] + 1) == skin.PADDING
    # Across: the overlay hides the strip within the window's padding on each side, so what shows starts a padding in
    # from the window's edges.
    overlay = compass_art('CompassOverlay')
    opaque = [x for x in range(overlay.width) if overlay.getpixel((x, 0))[3] == 255]
    assert opaque == [*range(skin.LEFT), *range(overlay.width - skin.LEFT, overlay.width)]
    assert b + skin.LEFT == skin.PADDING


# The spell book

BOOK_MEMPAGES = ('SBW_MemPage0_Button', 'SBW_MemPage1_Button')
# What the client writes into, a StaticText each: every element SIDL.xml gives the type, and nothing else.
STATIC_TEXT_ELEMENTS = ['ScreenID', 'Font', 'RelativePosition', 'Location', 'Size', 'Text', 'TextColor', 'NoWrap',
                        'AlignCenter', 'AlignRight']


def spellbook_parts():
    root, window = screen(skin.SPELLBOOK_FILE)
    return root, window, {e.findtext('ScreenID') or e.get('item'): e for e in direct_pieces(root, window)}


def check_static_text(text, align_right=False, align_center=False, wrap=False, color=skin.TEXT_RGB):
    """text is a StaticText the client writes into, empty until then, in font 3 and color (the text's), on one line or
    wrapping."""
    assert text.tag == 'StaticText' and [e.tag for e in text] == STATIC_TEXT_ELEMENTS
    assert text.findtext('Text') == '' and text.findtext('Font') == str(skin.TEXT_FONT)
    assert rgb(text, 'TextColor') == color and text.findtext('NoWrap') == str(not wrap).lower()
    assert text.findtext('AlignCenter') == str(align_center).lower()
    assert text.findtext('AlignRight') == str(align_right).lower()


def book_tile(n):
    """Spell n's tile's left and its frame's top: two across by four down each page, the stock reading order, the
    tiles side by side and the first row's frames a padding under the pages' top edge."""
    page, spot = divmod(n, skin.BOOK_PAGE_SPELLS)
    row, column = divmod(spot, skin.BOOK_COLUMNS)
    return (skin.BOOK_PAGE_XS[page] + column * skin.BOOK_TILE_WIDTH,
            skin.BOOK_PAGES_TOP + skin.PADDING + row * skin.BOOK_ROW_HEIGHT)


def stretched_reach(art, width, height):
    """Where art's opaque pixels can land when the client stretches it to width x height: their box scaled, and a pixel
    more on every side for the filtering, as (left, top, right, bottom), right and bottom exclusive."""
    marked = [(x, y) for x in range(art.width) for y in range(art.height) if art.getpixel((x, y))[3]]
    across, down = width / art.width, height / art.height
    return (math.floor(min(x for x, _ in marked) * across) - 1, math.floor(min(y for _, y in marked) * down) - 1,
            math.ceil((max(x for x, _ in marked) + 1) * across) + 1,
            math.ceil((max(y for _, y in marked) + 1) * down) + 1)


def harmful_reach(slot_size):
    """Where RedIconBackground's red can land, stretched to a slot of slot_size (see stretched_reach)."""
    anims = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')
    return stretched_reach(cut(decode(files()[skin.PIECES_TEXTURE]), anims['RedIconBackground']), *slot_size)


def item_icon_button():
    """The item window's icon button and its size, from its anchors."""
    button = {e.findtext('ScreenID'): e for e in parse(skin.ITEM_FILE).iter('Button')}['IconButton']
    return button, (number(button, 'RightAnchorOffset') - number(button, 'LeftAnchorOffset'),
                    number(button, 'BottomAnchorOffset') - number(button, 'TopAnchorOffset'))


def test_spellbook_keeps_every_control_the_client_looks_for():
    # eqgame.exe looks up the 16 spell slots and their names, the page arrows, the two memorize-page buttons (no size in
    # every skin), the page numbers and Done, and finds the bars by EQType, 9 memorizing and 10 scribing. The stock book
    # art (SBW_SpellBook1 to 4) is nothing it looks up, so it's left out. Drawn in this order: the bars, the pages with
    # the frames on them, the slots, the names, the page strips, then the band. No grid lines. With no title bar or
    # close box: it drags by its background, and Done closes it.
    root, window = check_inside_frame(skin.SPELLBOOK_FILE, skin.SPELLBOOK_WIDTH)
    assert window.get('item') == 'SpellBookWnd' and window.findtext('Text') == 'Spell Book'
    assert window.findtext('TooltipReference') == 'Your Spell Book'
    assert window.findtext('Style_Sizable') == window.findtext('Style_Closebox') == 'false'
    assert window.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    assert box(window)[2:] == (skin.SPELLBOOK_WIDTH, skin.SPELLBOOK_HEIGHT) == (497, 436)
    pieces = direct_pieces(root, window)
    assert [(e.tag, e.findtext('ScreenID')) for e in pieces] == [
        ('Gauge', 'SBW_Memorize_Gauge'), ('Gauge', 'SBW_Scribe_Gauge'), ('StaticAnimation', None),
        *(('Button', f'SBW_Spell{n}') for n in range(16)), *(('StaticText', f'SBW_SpellName{n}') for n in range(16)),
        ('Button', 'SBW_PageDown_Button'), ('Button', 'SBW_PageUp_Button'), ('StaticText', 'SBW_LeftPageNum'),
        ('StaticText', 'SBW_RightPageNum'), ('Button', 'DoneButton'), *(('Button', screen_id) for screen_id in BOOK_MEMPAGES)]
    assert pieces[2].get('item') == 'TUI_SBW_Pages' and pieces[2].findtext('Animation') == 'TUI_BookSpread'
    assert not [name for name in items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation') if 'BookRowDivider' in name
                or name == 'TUI_BookDivider']
    assert [number(e, 'EQType') for e in pieces if e.tag == 'Gauge'] == [skin.MEMORIZE_TYPE, skin.SCRIBE_TYPE] == [9, 10]
    assert not [e for e in root.iter() if (e.findtext('ScreenID') or '').startswith('SBW_SpellBook')]
    assert all((box(e)[2:] == (0, 0)) == (e.findtext('ScreenID') in BOOK_MEMPAGES) for e in pieces)
    for hidden in (e for e in pieces if e.findtext('ScreenID') in BOOK_MEMPAGES):
        assert {e.text for e in hidden.find('ButtonDrawTemplate')} == {'TUI_Clear'}


def test_spellbook_pages_hold_framed_icons_in_the_stock_reading_order():
    # Spells 0 to 7 on the left page and 8 to 15 on the right, two across by four down in the stock reading order. Each
    # slot is the stock book's, 44px round the icon's own 40px, 2px in all round (see
    # test_spellbook_and_item_window_hide_the_harmful_bars_under_the_icon), a pixel inside its frame, which is centered
    # across its tile. The name under it, a padding in from the tile's sides, centered and wrapping onto three lines, in
    # the book's ink.
    _, _, found = spellbook_parts()
    assert (skin.BOOK_ICON, skin.BOOK_SLOT_MARGIN, skin.BOOK_SLOT, skin.BOOK_FRAME) == (40, 2, 44, 46)
    assert (skin.BOOK_TILE_WIDTH, skin.BOOK_ROW_HEIGHT, skin.BOOK_NAME_WIDTH, skin.BOOK_NAME_LINES) == (100, 96, 88, 3)
    assert skin.book_frames() == [(x + skin.BOOK_FRAME_X, top) for x, top in map(book_tile, range(skin.BOOK_SPELLS))]
    for n in range(skin.BOOK_SPELLS):
        x, top = book_tile(n)
        slot = found[f'SBW_Spell{n}']
        slot_box = box(slot)
        line = skin.BOOK_FRAME_LINE
        assert slot_box == (x + skin.BOOK_FRAME_X + line, top + line, skin.BOOK_SLOT, skin.BOOK_SLOT)
        assert [(e.tag, e.text) for e in slot.find('ButtonDrawTemplate')] == [
            ('Normal', 'TUI_BookSlot'), ('Pressed', 'TUI_BookSlotPressed'), ('Flyby', 'TUI_BookSlotFlyby'),
            ('PressedFlyby', 'TUI_BookSlotPressed'), ('NormalDecal', skin.BUFF_ICONS)]
        decal = (number(slot, 'DecalOffset/X'), number(slot, 'DecalOffset/Y'))
        assert decal == (skin.BOOK_SLOT_MARGIN, skin.BOOK_SLOT_MARGIN)
        assert (number(slot, 'DecalSize/CX'), number(slot, 'DecalSize/CY')) == (skin.BOOK_ICON, skin.BOOK_ICON)
        icon_left = slot_box[0] + decal[0]
        assert icon_left - x == x + skin.BOOK_TILE_WIDTH - (icon_left + skin.BOOK_ICON) == 30  # centered on the tile
        assert slot.findtext('Style_Checkbox') == 'false' and slot.find('TooltipReference') is None
        name = found[f'SBW_SpellName{n}']
        assert box(name) == (x + skin.PADDING, top + skin.BOOK_NAME_TOP, skin.BOOK_NAME_WIDTH,
                             skin.BOOK_NAME_LINES * skin.TEXT_HEIGHT)
        assert box(name)[0] + box(name)[2] + skin.PADDING == x + skin.BOOK_TILE_WIDTH
        check_static_text(name, align_center=True, wrap=True, color=skin.BOOK_INK_RGB)
    # Reading order: the next spell beside, then the row under.
    assert box(found['SBW_Spell1'])[1] == box(found['SBW_Spell0'])[1] < box(found['SBW_Spell2'])[1]
    assert box(found['SBW_Spell1'])[0] > box(found['SBW_Spell0'])[0] == box(found['SBW_Spell2'])[0]
    assert box(found['SBW_Spell8'])[1] == box(found['SBW_Spell0'])[1]
    assert skin.BOOK_PAGE_WIDTH == 2 * skin.BOOK_TILE_WIDTH


def test_spellbook_names_fit_their_lines():
    # Every name a class can scribe (spells_en.txt: the name in field 1, the 15 class levels in fields 92 to 106, 255
    # for none) wraps onto BOOK_NAME_LINES at BOOK_NAME_WIDTH in font 3, but two single words with no space to wrap at.
    preview = preview_module()
    spells = next((Path(folder) / 'spells_en.txt' for folder in EQ_DIRS
                   if folder and (Path(folder) / 'spells_en.txt').is_file()), None)
    if spells is None or not any(Path(path).is_file() for path in preview.ARIAL):
        pytest.skip('no spells_en.txt or no Arial here')
    face = preview.font(skin.TEXT_FONT)
    names = set()
    for line in spells.read_text(encoding='latin-1').splitlines():
        fields = line.split('^')
        if len(fields) > 106 and any(level.strip() not in ('', '255') for level in fields[92:107]):
            names.add(fields[1])
    assert len(names) > 1000
    lines = {name: preview.wrapped(name, face, skin.BOOK_NAME_WIDTH) for name in names}
    assert all(len(wrapped) <= skin.BOOK_NAME_LINES for wrapped in lines.values())
    too_wide = {name for name, wrapped in lines.items() if any(face.getlength(w) > skin.BOOK_NAME_WIDTH for w in wrapped)}
    assert too_wide <= {'VampEmbraceNecro', 'VampEmbraceShadow'}
    assert max(len(wrapped) for wrapped in lines.values()) == skin.BOOK_NAME_LINES


def test_spellbook_text_has_only_what_the_stock_schema_gives_static_text():
    # SIDL.xml makes StaticText a static piece (a ScreenPiece, then a StaticScreenPiece): no EQType, AlignLeft or
    # Style_ flags, which label() writes.
    types = stock_sidl()
    allowed ={name for kind in ('ScreenPiece', 'StaticScreenPiece', 'StaticText')
               for name in re.findall(r'<element name="(\w+)"', types[kind])}
    assert set(STATIC_TEXT_ELEMENTS) <= allowed and not {'EQType', 'AlignLeft', 'Style_Transparent'} & allowed


def test_spellbook_follows_the_spacing_standard():
    _, window, found = spellbook_parts()
    b = skin.BORDER
    line = skin.BOOK_FRAME_LINE
    # Down: the bar a padding under the window's edge, the pages a padding under it, and the first frames a padding
    # under the pages' top edge.
    bar, pages = box(found['SBW_Memorize_Gauge']), box(found['TUI_SBW_Pages'])
    assert b + bar[1] == skin.PADDING and pages[1] - (bar[1] + bar[3]) == skin.PADDING
    assert box(found['SBW_Spell0'])[1] - line - pages[1] == skin.PADDING
    assert box(found['SBW_Spell8'])[1] == box(found['SBW_Spell0'])[1]
    # In each tile, the name's ink a padding under the frame, and a three-line name's letters a padding over the next
    # row's frame, or on the last row over the pages' bottom edge (each rounded up to a whole pixel).
    for n in range(skin.BOOK_SPELLS):
        slot, name = box(found[f'SBW_Spell{n}']), box(found[f'SBW_SpellName{n}'])
        assert 0 <= name[1] + skin.TEXT_INK_TOP - (slot[1] + slot[3] + line) - skin.PADDING < 1, n
        letters_bottom = name[1] + (skin.BOOK_NAME_LINES - 1) * skin.TEXT_HEIGHT + skin.BOOK_INK_BOTTOM
        last_row = n % skin.BOOK_PAGE_SPELLS >= skin.BOOK_PAGE_SPELLS - skin.BOOK_COLUMNS
        below = pages[1] + pages[3] if last_row else box(found[f'SBW_Spell{n + skin.BOOK_COLUMNS}'])[1] - line
        assert 0 <= below - letters_bottom - skin.PADDING < 1, n
    assert skin.BOOK_INK_BOTTOM == skin.TEXT_HEIGHT - 1.5  # where the digits end (see the spacing standard)
    # Across: Previous at the window's padding, the pages a padding past it, each name a padding in from its tile's
    # sides (the tiles meet, so two names are two paddings apart), the crease a padding past the left page and a padding
    # before the right page, Next a padding past the pages and a padding from the window's edge.
    down, up = box(found['SBW_PageDown_Button']), box(found['SBW_PageUp_Button'])
    assert b + down[0] == skin.PADDING and pages[0] - (down[0] + down[2]) == skin.PADDING
    assert (pages[0], pages[0] + pages[2]) == (skin.BOOK_PAGE_XS[0], skin.BOOK_PAGE_XS[1] + skin.BOOK_PAGE_WIDTH)
    for page, left in enumerate(skin.BOOK_PAGE_XS):
        first, second = (box(found[f'SBW_SpellName{page * skin.BOOK_PAGE_SPELLS + c}']) for c in (0, 1))
        assert first[0] - left == left + skin.BOOK_PAGE_WIDTH - (second[0] + second[2]) == skin.PADDING
        assert second[0] - (first[0] + first[2]) == 2 * skin.PADDING
    crease = skin.BOOK_CREASE_X
    assert crease - (skin.BOOK_PAGE_XS[0] + skin.BOOK_PAGE_WIDTH) == skin.PADDING
    assert skin.BOOK_PAGE_XS[1] - (crease + 1) == skin.PADDING
    assert up[0] - (pages[0] + pages[2]) == skin.PADDING and box(window)[2] - (b + up[0] + up[2]) == skin.PADDING
    # The band a padding under the pages: the page numbers a padding from the strips with their digits' ink centered
    # on the band, and Done centered on the crease.
    band = pages[1] + pages[3] + skin.PADDING
    first, second = box(found['SBW_LeftPageNum']), box(found['SBW_RightPageNum'])
    assert first[0] == down[0] + down[2] + skin.PADDING and second[0] + second[2] == up[0] - skin.PADDING
    for number_box in (first, second):
        assert number_box[1] + skin.DIGITS_INK_MIDDLE == band + skin.TEXT_BUTTON_HEIGHT / 2
        assert number_box[2:] == (skin.NUMBER_WIDTH, skin.TEXT_HEIGHT)
    done = box(found['DoneButton'])
    assert done[1] == band and done[3] == skin.TEXT_BUTTON_HEIGHT
    assert abs(done[0] + done[2] / 2 - (crease + 0.5)) <= 0.5
    # The strips from the bar's top to Done's bottom, and the window's edge a padding under the band.
    for strip in (down, up):
        assert strip[1] == bar[1] and strip[1] + strip[3] == done[1] + done[3]
    assert box(window)[3] - (b + done[1] + done[3]) == skin.PADDING


def test_spellbook_page_strips_run_down_the_sides():
    # Previous and Next as strips as tall as the window's inside, where they never move: the Actions window's arrows
    # drawn at the strip's size, a chevron centered on each, from the book's own texture, since they're too tall for the
    # atlas.
    _, _, found = spellbook_parts()
    anims = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')
    texture = decode(files()[skin.BOOK_TEXTURE])
    assert texture.size == (skin.BOOK_TEXTURE_WIDTH, skin.BOOK_TEXTURE_HEIGHT) == (1024, 512)
    for screen_id, tooltip, icon in (('SBW_PageDown_Button', 'Previous Page', 'Left'),
                                     ('SBW_PageUp_Button', 'Next Page', 'Right')):
        strip = found[screen_id]
        assert box(strip)[2:] == (skin.BOOK_TURN_WIDTH, skin.BOOK_TURN_HEIGHT) == (30, 424)
        assert strip.findtext('TooltipReference') == tooltip and strip.findtext('Style_Checkbox') == 'false'
        assert [(e.tag, e.text) for e in strip.find('ButtonDrawTemplate')] == [
            (state, f'TUI_TogglePage{icon}{skin.ICON_ART[state]}') for state in skin.BUTTON_STATES]
        for state in skin.ICON_LOOKS:
            anim = anims[f'TUI_TogglePage{icon}{state}']
            assert anim.findtext('Frames/Texture') == skin.BOOK_TEXTURE
            art = cut(texture, anim)
            drawn = skin.toggle_art(skin.icon_coverage(skin.ARROW_ICONS[icon]), state, skin.BOOK_TURN_WIDTH,
                                    skin.BOOK_TURN_HEIGHT)
            assert pixels(art) == [p for row in skin.snapped_art(drawn).rows for p in row], (icon, state)


def test_spellbook_band_is_the_page_numbers_and_the_loot_windows_done():
    _, _, found = spellbook_parts()
    check_static_text(found['SBW_LeftPageNum'])
    check_static_text(found['SBW_RightPageNum'], align_right=True)
    # Done as wide as the loot and bank windows', with no tooltip (the stock Done has none).
    check_confirmation_button(found['DoneButton'], 'Done')
    loot_done = {e.findtext('ScreenID'): e for e in parse(skin.LOOT_FILE).iter('Button')}['DoneButton']
    assert box(found['DoneButton'])[2] == box(loot_done)[2] == skin.BOOK_DONE_WIDTH == 78


def test_spellbook_bars_share_one_spot_along_the_top():
    # Memorizing and scribing never run together, so both bars share the spot along the top, the spell bar's recovery
    # bar across both pages: as thin and in the same soft red, with no track, so nothing shows while neither runs, and
    # their own text hidden.
    _, _, found = spellbook_parts()
    recovery = {e.findtext('ScreenID'): e for e in parse(skin.CASTSPELL_FILE).iter('Gauge')}['CSPW_Global_Recast']
    for screen_id in ('SBW_Memorize_Gauge', 'SBW_Scribe_Gauge'):
        bar = found[screen_id]
        assert box(bar) == (skin.BOOK_LEFT, skin.BOOK_BAR_TOP, skin.BOOK_CONTENT_WIDTH, skin.TICK_HEIGHT)
        pages = box(found['TUI_SBW_Pages'])
        assert (box(bar)[0], box(bar)[0] + box(bar)[2]) == (pages[0], pages[0] + pages[2])
        assert [(e.tag, e.text) for e in bar.find('GaugeDrawTemplate')] == [('Fill', 'TUI_MemorizeFill')]
        assert rgb(bar, 'FillTint') == rgb(recovery, 'FillTint') == skin.SPELL_RGB
        assert box(bar)[3] == box(recovery)[3]
        assert number(bar, 'GaugeOffsetY') == 0 and number(bar, 'TextOffsetY') == 8000
    fill = cut(decode(files()[skin.PIECES_TEXTURE]), items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')['TUI_MemorizeFill'])
    assert fill.size == (skin.BOOK_CONTENT_WIDTH, skin.TICK_HEIGHT) and set(pixels(fill)) == {skin.BAR_FILL}


def test_spellbook_slots_are_clear_whatever_the_client_paints_on_them():
    # The client names A_SpellBookSlot itself (eqgame.exe, beside the spellbook's ScreenIDs), most likely an empty
    # slot's look: default's is a dark 48px square. It's redefined clear at a slot's size, like the slot's own art, and
    # the base's definition taken out.
    assert 'A_SpellBookSlot' in skin.REPLACED_ANIMATIONS
    assert files()[skin.ANIMATIONS_FILE].decode('latin-1').count('item="A_SpellBookSlot"') == 1
    anims = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')
    atlas = decode(files()[skin.PIECES_TEXTURE])
    for name in ('A_SpellBookSlot', 'TUI_BookSlot'):
        art = cut(atlas, anims[name])
        assert art.size == (skin.BOOK_SLOT, skin.BOOK_SLOT) and {p[3] for p in pixels(art)} == {0}, name
    base = BASE_ANIMATIONS.replace('</XML>', '  <Ui2DAnimation item="A_SpellBookSlot"></Ui2DAnimation>\r\n</XML>')
    assert 'A_SpellBookSlot' in base and 'A_SpellBookSlot' not in skin.with_definitions(base, [])


def test_spellbook_pages_are_parchment_with_the_frames_on_them():
    # The book's own look (see PARCHMENT_RGB): the pages one picture from the book's texture, parchment inside a rounded
    # darker edge, with a grain and darker toward the crease between the pages, the crease a line of its own, and each
    # spell's frame drawn on them a pixel outside its slot, the page showing inside it. Every green on the 16 steps, so
    # the client dithers nothing, and the grain the same every build.
    _, _, found = spellbook_parts()
    anim = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')['TUI_BookSpread']
    assert anim.findtext('Frames/Texture') == skin.BOOK_TEXTURE
    art = cut(decode(files()[skin.BOOK_TEXTURE]), anim)
    pages = box(found['TUI_SBW_Pages'])
    assert art.size == pages[2:] == (skin.BOOK_CONTENT_WIDTH, skin.BOOK_PAGES_HEIGHT) == (413, 390)
    assert pixels(art) == [p for row in skin.snapped_art(skin.book_spread()).rows for p in row]
    assert all(p[1] % skin.STEP == 0 and p[3] % skin.STEP == 0 for p in pixels(art))
    width, height = art.size
    corner = skin.CORNER_RADIUS
    assert {art.getpixel((x, y))[3] for x in range(width) for y in range(height)
            if corner <= x < width - corner or corner <= y < height - corner} == {255}  # opaque but at the corners
    assert art.getpixel((0, 0))[3] < 255 and art.getpixel((width // 4, 0)) == (*skin.BOOK_PAGE_EDGE_RGB, 255)
    crease = skin.BOOK_CREASE_X - pages[0]
    assert {art.getpixel((crease, y)) for y in range(1, height - 1)} == {(*skin.BOOK_CREASE_RGB, 255)}

    def page(columns):
        return [art.getpixel((x, y)) for x in columns for y in range(1, height - 1)]

    away = page(range(1, skin.BOOK_FRAME_X))  # the left page's margin, clear of the frames
    beside = page([*range(crease - 3, crease), *range(crease + 1, crease + 4)])
    assert all(abs(sum(p[c] for p in away) / len(away) - skin.PARCHMENT_RGB[c]) < 10 for c in range(3))
    assert sum(p[1] for p in beside) / len(beside) < sum(p[1] for p in away) / len(away) - 2 * skin.STEP
    greens = {p[1] for p in away}
    assert {skin.PARCHMENT_RGB[1] - skin.STEP, skin.PARCHMENT_RGB[1] + skin.STEP} <= greens  # the grain
    for n in range(skin.BOOK_SPELLS):
        x, y = (a - b - skin.BOOK_FRAME_LINE for a, b in zip(box(found[f'SBW_Spell{n}'])[:2], pages[:2]))
        far = skin.BOOK_FRAME - 1
        sides = [(x + k, y + edge) for k in range(corner, skin.BOOK_FRAME - corner) for edge in (0, far)]
        sides += [(x + edge, y + k) for k in range(corner, skin.BOOK_FRAME - corner) for edge in (0, far)]
        assert {art.getpixel(p) for p in sides} == {(*skin.BOOK_FRAME_RGB, 255)}, n
        ring = [(x + k, y + edge) for k in range(corner, skin.BOOK_FRAME - corner) for edge in (1, 2, far - 1)]
        assert all(art.getpixel(p)[1] >= skin.PARCHMENT_RGB[1] - skin.STEP for p in ring), n


def test_spellbook_names_are_dark_ink_that_reads_on_the_parchment():
    # The names in BOOK_INK_RGB, like the stock book's black names on its parchment: at least 7 to 1 against the page
    # (WCAG's AAA for text), where the page numbers, on the cover, keep the text's color.
    def luminance(color):
        linear = [(c / 255 / 12.92 if c / 255 <= 0.04045 else ((c / 255 + 0.055) / 1.055) ** 2.4) for c in color]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    _, _, found = spellbook_parts()
    assert {rgb(found[f'SBW_SpellName{n}'], 'TextColor') for n in range(skin.BOOK_SPELLS)} == {skin.BOOK_INK_RGB}
    assert (luminance(skin.PARCHMENT_RGB) + 0.05) / (luminance(skin.BOOK_INK_RGB) + 0.05) >= 7
    assert rgb(found['SBW_LeftPageNum'], 'TextColor') == skin.TEXT_RGB


def test_spellbook_ring_lights_round_the_icon_under_the_pointer():
    # Hovered, and pressed, a slot shows a gold ring BOOK_SLOT_MARGIN wide round its icon, darker pressed, its outside
    # rounded like the panel's corners and its inside clear, so the spell a click takes shows before the click, and on
    # an empty spot the page shows through. Every color on the 16 steps.
    anims = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')
    atlas = decode(files()[skin.PIECES_TEXTURE])
    size, margin, corner = skin.BOOK_SLOT, skin.BOOK_SLOT_MARGIN, skin.CORNER_RADIUS
    assert set(skin.BOOK_RING_RGB) == {'Flyby', 'Pressed'}
    assert sum(skin.BOOK_RING_RGB['Flyby']) > sum(skin.BOOK_RING_RGB['Pressed'])
    for state, color in skin.BOOK_RING_RGB.items():
        assert skin.snapped((*color, 255)) == (*color, 255)
        art = cut(atlas, anims[f'TUI_BookSlot{state}'])
        assert art.size == (size, size)
        icon = range(margin, size - margin)
        inside = [art.getpixel((x, y)) for x in icon for y in icon]
        assert {p[3] for p in inside} == {0}, state
        ring = [art.getpixel((x, y)) for x in range(size) for y in range(size) if not (x in icon and y in icon)]
        assert {p[:3] for p in ring} == {color}, state
        sides = [(x, y) for x in range(corner, size - corner) for y in (*range(margin), *range(size - margin, size))]
        assert all(art.getpixel(p)[3] == art.getpixel(p[::-1])[3] == 255 for p in sides), state
        assert art.getpixel((0, 0))[3] < 255  # a rounded corner


def test_spellbook_and_item_window_hide_the_harmful_bars_under_the_icon():
    # The client paints a detrimental spell's slot RedIconBackground, the Effects window's art, stretched to the slot:
    # in game, its bars stood left of the icon down most of a 100 by 92 tile. Wherever the stretched bars can land, a
    # pixel of filtering round them included, lies inside the icon: in the spell book, the stock book's slot, 44px with
    # the icon 2px in (48 with the icon at 4 lets red onto the row above the icon), and in the item window, whose icon
    # button is the icon's size. Every book slot lies wholly inside the window's inside, where the client hit-tests it
    # (see SLOT_WIDTH).
    _, window, found = spellbook_parts()
    inside = (box(window)[2] - 2 * skin.BORDER, box(window)[3] - 2 * skin.BORDER)
    reach = harmful_reach((skin.BOOK_SLOT, skin.BOOK_SLOT))
    assert reach == (5, 3, 12, 41)
    for n in range(skin.BOOK_SPELLS):
        slot = found[f'SBW_Spell{n}']
        x, y, width, height = box(slot)
        assert 0 <= x and x + width <= inside[0] and 0 <= y and y + height <= inside[1]
        left, top = number(slot, 'DecalOffset/X'), number(slot, 'DecalOffset/Y')
        right, bottom = left + number(slot, 'DecalSize/CX'), top + number(slot, 'DecalSize/CY')
        assert left <= reach[0] and top <= reach[1] and reach[2] <= right and reach[3] <= bottom, n
    assert harmful_reach((48, 48))[1] < 4  # the slot tried bigger, with the icon at 4
    button, button_size = item_icon_button()
    assert button_size == (skin.ITEM_ICON, skin.ITEM_ICON)
    assert (number(button, 'DecalOffset/X'), number(button, 'DecalOffset/Y')) == (0, 0)
    assert (number(button, 'DecalSize/CX'), number(button, 'DecalSize/CY')) == button_size
    item_reach = harmful_reach(button_size)
    assert item_reach == (4, 3, 11, 37) and min(item_reach) >= 0 and max(item_reach) <= skin.ITEM_ICON


def test_spell_icons_are_opaque_under_the_harmful_bars():
    # The book's and item window's icons are A_SpellIcons cells (40px, ours) drawn at their own size. Wherever the
    # stretched red bars can land under one (see harmful_reach), every cell is opaque, so no red shows through: only
    # a tile's rounded corners are see-through, clear of them.
    cell = skin.BOOK_ICON
    assert skin.ITEM_ICON == cell == 40
    margin = skin.BOOK_SLOT_MARGIN
    left, top, right, bottom = harmful_reach((skin.BOOK_SLOT, skin.BOOK_SLOT))
    regions = [(range(left - margin, right - margin), range(top - margin, bottom - margin)),  # in the icon's pixels
               (lambda r: (range(r[0], r[2]), range(r[1], r[3])))(harmful_reach(item_icon_button()[1]))]
    assert regions[0] == (range(3, 10), range(1, 39)) and regions[1] == (range(4, 11), range(3, 37))
    for n in range(skin.SPELL_ICON_CELLS):
        alpha = spell_icon(n).getchannel('A')
        for columns, rows in regions:
            assert all(alpha.getpixel((x, y)) == 255 for x in columns for y in rows), n
        assert {alpha.getpixel((x, y)) for x in (0, cell - 1) for y in (0, cell - 1)} == {0}  # the rounded corners


@functools.cache
def icon_sheet(name):
    return decode(files()[name])


def spell_icon(cell, size=skin.BOOK_ICON):
    """Our icon for a spell icon cell at size, cut from the built sheets where the client finds it: left to right and
    down each sheet, running on to the next."""
    names = skin.SPELL_ICON_SHEETS if size == skin.BOOK_ICON else skin.GEM_ICON_SHEETS
    across = skin.ICON_SHEET // size
    sheet, spot = divmod(cell, across * across)
    x, y = spot % across * size, spot // across * size
    return icon_sheet(names[sheet]).crop((x, y, x + size, y + size))


BATCH_ONE = {161, 51, 42, 99, 56, 41, 1, 153, 38, 37, 16, 17, 4, 35, 18, 117}  # the most-used pictures, drawn first
BATCH_TWO = {0, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 25, 26, 27, 36, 40, 47, 82, 88, 91, 95, 102, 109, 114, 118, 119, 140,
             163}  # hands, body and mind
BATCH_THREE = {46, 52, 53, 57, 58, *range(60, 71), 77, 78, 90, 96, 98, 128, *range(130, 134), *range(148, 153), *range(155, 159)}
# shields and armor
BATCH_FOUR = {19, 23, 31, 33, 34, 44, 45, 48, *range(73, 77), 79, 80, *range(85, 88), *range(92, 95), 97, 101, 103, *range(106, 109),
              112, 113, *range(120, 123), 129, 137}  # eyes, sight and travel
BATCH_FIVE = {2, 3, 5, 20, 21, 22, 24, 28, 29, 30, 32, 39, 43, 49, 50, 54, 55, 59, 71, 72, 81, 83, 84, 89, 100, 104, 105, 110,
              111, 115, 116, *range(123, 128), 134, 135, 136, 138, 139, *range(141, 148), 154, 159, 160, 162, 164, 165}
# elements, nature, creatures and weapons


def test_every_spell_icon_cell_has_a_tile():
    # 200 cells in A_SpellGems, the first 180 in A_SpellIcons too, as the stock sheets have: each in exactly one tile,
    # every tile defined, and each picture a cell's. The most-used pictures are drawn.
    assert (skin.SPELL_ICON_CELLS, skin.GEM_ICON_CELLS) == (180, 200)
    cells = [cell for group in skin.SPELL_TILE_CELLS.values() for cell in group]
    assert sorted(cells) == list(range(skin.GEM_ICON_CELLS))
    assert set(skin.SPELL_TILE_CELLS) == set(skin.SPELL_TILES) and len(skin.SPELL_TILES) == 14
    assert all(len(palette) == 3 for palette in skin.SPELL_TILES.values())
    assert set(skin.SPELL_PICTURES) <= set(range(skin.GEM_ICON_CELLS)) and BATCH_ONE | BATCH_TWO | BATCH_THREE | BATCH_FOUR | BATCH_FIVE <= set(skin.SPELL_PICTURES)
    assert (len(BATCH_THREE), len(BATCH_FOUR), len(BATCH_FIVE)) == (35, 33, 54)
    # Every cell a Quarm spell uses is painted (spells_en.txt's field 131 runs 0 to 165).
    assert set(range(166)) <= set(skin.SPELL_PICTURES)
    assert skin.SPELL_TILE[99] == 'blue' and skin.SPELL_TILE[51] == 'orange' and skin.SPELL_TILE[161] == 'red'


def test_spell_icon_animations_are_ours_over_our_sheets():
    # The client names A_SpellIcons and A_SpellGems itself and reads them as grids, cell n the nth left to right and
    # down, running on from one frame's texture to the next: ours, each sheet the stock ones' size, defined once.
    root = parse(skin.ANIMATIONS_FILE)
    anims = items(root, 'Ui2DAnimation')
    textures = items(root, 'TextureInfo')
    data = files()[skin.ANIMATIONS_FILE].decode('latin-1')
    for name, sheets, cell in (('A_SpellIcons', skin.SPELL_ICON_SHEETS, skin.BOOK_ICON),
                               ('A_SpellGems', skin.GEM_ICON_SHEETS, skin.GEM_ICON)):
        anim = anims[name]
        assert data.count(f'item="{name}"') == 1 and name in skin.REPLACED_ANIMATIONS
        assert [anim.findtext(tag) for tag in ('Cycle', 'Grid', 'Vertical')] == ['false', 'true', 'false']
        assert number(anim, 'CellWidth') == number(anim, 'CellHeight') == cell
        frames = anim.findall('Frames')
        assert [frame.findtext('Texture') for frame in frames] == list(sheets)
        for frame in frames:
            assert rect_of_frame(frame) == (0, 0, skin.ICON_SHEET, skin.ICON_SHEET)
            assert box_size(textures[frame.findtext('Texture')]) == (skin.ICON_SHEET, skin.ICON_SHEET)
            assert icon_sheet(frame.findtext('Texture')).size == (skin.ICON_SHEET, skin.ICON_SHEET)
    assert len(skin.SPELL_ICON_SHEETS) * 36 == skin.SPELL_ICON_CELLS and len(skin.GEM_ICON_SHEETS) * 100 == 200


def rect_of_frame(frame):
    return (number(frame, 'Location/X'), number(frame, 'Location/Y'), number(frame, 'Size/CX'), number(frame, 'Size/CY'))


def box_size(texture_info):
    return number(texture_info, 'Size/CX'), number(texture_info, 'Size/CY')


@pytest.mark.parametrize('size', [skin.BOOK_ICON, skin.GEM_ICON])
def test_spell_icons_are_rounded_tiles_with_their_edge_kept_clear(size):
    # Every cell a rounded tile: clear corners keeping the panel's color (so filtering never darkens them), opaque
    # inside. Cells of one tile with no picture yet are the same plain tile; the tiles differ. A picture never paints
    # over its tile's outermost pixels, the edge line's, so every tile keeps a clean edge.
    cells = skin.SPELL_ICON_CELLS if size == skin.BOOK_ICON else skin.GEM_ICON_CELLS
    plain = {}
    for tile, group in skin.SPELL_TILE_CELLS.items():
        bare = [cell for cell in group if cell < cells and cell not in skin.SPELL_PICTURES]
        if bare:
            plain[tile] = pixels(spell_icon(bare[0], size))
            assert all(pixels(spell_icon(cell, size)) == plain[tile] for cell in bare), tile
    assert len({tuple(p) for p in plain.values()}) == len(plain)
    ring = [(x, y) for x in range(size) for y in range(size) if x in (0, size - 1) or y in (0, size - 1)]
    middle = size // 2
    for cell in range(cells):
        icon = spell_icon(cell, size)
        assert icon.getpixel((0, 0)) == icon.getpixel((size - 1, size - 1)) == skin.CLEAR, cell
        assert icon.getpixel((middle, middle))[3] == icon.getpixel((1, middle))[3] == 255, cell
        tile = skin.SPELL_TILE[cell]
        if tile in plain:
            assert all(icon.getpixel(p) == plain[tile][p[1] * size + p[0]] for p in ring), cell
    past = icon_sheet(skin.SPELL_ICON_SHEETS[0]).crop((6 * skin.BOOK_ICON, 0, skin.ICON_SHEET, skin.ICON_SHEET))
    assert past.getextrema()[3] == (0, 0)  # what's past the 6 by 6 cells is clear


def test_a_spell_picture_is_painted_over_its_tile():
    # Every drawn cell differs from its plain tile inside the edge, at both sizes, the same picture at each.
    for size in (skin.BOOK_ICON, skin.GEM_ICON):
        for cell in (c for c in skin.SPELL_PICTURES if size == skin.GEM_ICON or c < skin.SPELL_ICON_CELLS):
            icon = spell_icon(cell, size)
            bare = next(c for c in skin.SPELL_TILE_CELLS[skin.SPELL_TILE[cell]] if c not in skin.SPELL_PICTURES)
            changed = sum(a != b for a, b in zip(pixels(icon), pixels(spell_icon(bare, size))))
            assert changed > size * size // 6, (cell, size)


def test_slot_backgrounds_are_clear_with_a_red_bar_each_side_of_a_harmful_icon():
    # The client paints helpful effects with BlueIconBackground and harmful ones with RedIconBackground,
    # the only sign of an effect's type a skin gets: the skin's are the slot's size (the client stretches
    # them to each slot), replacing the base's own. Clear, so the row is the panel at the window's own alpha (solid
    # rows in the panel's color showed as darker stripes at Alpha 205 in game), and a harmful effect's has
    # a solid red bar 4px wide on each side of the icon, touching it, as tall as the icon (the user's
    # design, after a faint red across the row, a red square behind the icon, which left a ring too faint to
    # see, and a single 5px bar between the icon and the name).
    data = files()[skin.ANIMATIONS_FILE].decode('latin-1')
    assert data.count('item="BlueIconBackground"') == data.count('item="RedIconBackground"') == 1
    anims = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')
    atlas = decode(files()[skin.PIECES_TEXTURE])
    blue = cut(atlas, anims['BlueIconBackground'])
    assert blue.size == (skin.SLOT_WIDTH, skin.ROW_HEIGHT)
    assert set(pixels(blue)) == {skin.HELPFUL_RGBA} == {skin.CLEAR} and skin.CLEAR[3] == 0
    red = cut(atlas, anims['RedIconBackground'])
    assert red.size == (skin.SLOT_WIDTH, skin.ROW_HEIGHT)
    assert skin.snapped(skin.HARMFUL_RGBA) == skin.HARMFUL_RGBA and skin.HARMFUL_RGBA[3] == 255
    assert skin.HARMFUL_BAR_WIDTH == 4
    # Within the slot, which the client puts at SLOT_X: level with the icon, one bar right after Zeal's time
    # column and ending where the icon starts, the other starting where the icon ends, a padding before the
    # name.
    icon_x = skin.ROW_ICON_X - skin.SLOT_X
    left, right = (x - skin.SLOT_X for x in skin.HARMFUL_BARS)
    assert left == skin.TIMER_WIDTH and left + skin.HARMFUL_BAR_WIDTH == icon_x
    assert right == icon_x + skin.ROW_ICON
    assert skin.ROW_NAME_X - (skin.SLOT_X + right + skin.HARMFUL_BAR_WIDTH) == skin.PADDING
    for x in range(skin.SLOT_WIDTH):
        for y in range(skin.ROW_HEIGHT):
            inside = (any(bar <= x < bar + skin.HARMFUL_BAR_WIDTH for bar in (left, right))
                      and skin.ROW_ICON_MARGIN <= y < skin.ROW_ICON_MARGIN + skin.ROW_ICON)
            assert red.getpixel((x, y)) == (skin.HARMFUL_RGBA if inside else skin.CLEAR), (x, y)
    # Only the redefined ones: every other stock definition stays.
    base = BASE_ANIMATIONS.replace('BlueIconBackground', 'SomethingElse')
    assert skin.with_definitions(base, []).count('SomethingElse') == 1


# The inventory window

# Every control of the stock window with a ScreenID. eqgame.exe looks up the slots (InvSlot%d), the coins (IW_Money%d),
# IW_Skills, IW_AltAdvBtn, IW_Destroy, DoneButton, ClassAnim, IW_CharacterView, AltAdvLabel and AltAdvGauge; the rest
# are kept like every stock control.
STOCK_INVENTORY = [
    *(f'InvSlot{n}' for n in range(1, 30)), 'NameLabel', 'LevelClassLabel', 'DeityLabel', 'HPLabel', 'HPNumberLabel',
    'ACLabel', 'ACNumberLabel', 'ATKLabel', 'ATKNumberLabel', 'NextLevelLabel', 'ExpGauge',
    *(f'{stat}{kind}' for stat in ('STR', 'STA', 'AGI', 'DEX', 'WIS', 'INT', 'CHA') for kind in ('Label', 'NumberLabel')),
    *(f'{resist}{kind}' for resist in ('Poison', 'Magic', 'Disease', 'Fire', 'Cold') for kind in ('Label', 'NumberLabel')),
    'WeightLabel', 'WeightNumberLabel', 'AltAdvLabel', 'AltAdvGauge', *(f'IW_Money{n}' for n in range(4)), 'IW_Skills',
    'IW_AltAdvBtn', 'IW_Destroy', 'ClassAnim', 'IW_CharacterView', 'DoneButton',
]
# Where the stock window has each worn slot, by EQType, on its 40px grid from x 120.
STOCK_WORN = {1: (120, 0), 2: (200, 0), 3: (240, 0), 4: (280, 0), 5: (160, 0), 6: (280, 80), 7: (120, 80),
              8: (280, 40), 9: (120, 120), 10: (280, 120), 11: (220, 280), 12: (280, 160), 13: (140, 280),
              14: (180, 280), 15: (120, 200), 16: (280, 200), 17: (120, 40), 18: (180, 240), 19: (220, 240),
              20: (120, 160), 21: (260, 280)}


def inventory_parts():
    root, window = screen(skin.INVENTORY_FILE)
    return root, window, {e.findtext('ScreenID') or e.get('item'): e for e in direct_pieces(root, window)}


def test_inventory_window_keeps_every_control_the_stock_one_has():
    # A fixed size with no title bar or close box (the user's pick, like the other windows), so it drags by its
    # background and Done closes it. The drop area comes first, so the middle's text draws over it.
    root, window = check_inside_frame(skin.INVENTORY_FILE, skin.INV_WIDTH)
    assert window.get('item') == 'InventoryWindow' and window.findtext('Text') == 'Inventory'
    assert window.findtext('TooltipReference') == 'Inventory'  # the stock window's
    assert window.findtext('Style_Sizable') == window.findtext('Style_Closebox') == 'false'
    assert window.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    assert box(window)[2:] == (skin.INV_WIDTH, skin.INV_HEIGHT) == (349, 326)
    pieces = direct_pieces(root, window)
    ids = [e.findtext('ScreenID') for e in pieces if e.findtext('ScreenID')]
    assert sorted(ids) == sorted(STOCK_INVENTORY) and len(set(ids)) == len(ids)
    assert pieces[0].findtext('ScreenID') == 'IW_CharacterView'
    for folder in EQ_DIRS:
        path = Path(folder) / 'uifiles' / 'default' / skin.INVENTORY_FILE
        if folder and path.is_file():
            stock = re.findall(r'<ScreenID>\s*(\w+)\s*</ScreenID>', path.read_text(encoding='latin-1'))
            assert sorted(stock) == sorted(STOCK_INVENTORY)
            break


def test_inventory_worn_slots_keep_the_stock_arrangement():
    # Each worn slot on the hot bar's squares, in the stock window's column and row, but for Legs and Feet, centered
    # between the rings a row higher, and the weapons under them. The bag slots stay with no size: the hot button window
    # has them (the user).
    _, _, found = inventory_parts()
    assert [eq_type for eq_type, *_ in skin.INV_WORN] == list(range(1, 22))
    raised = {18, 19, 11, 13, 14, 21}
    for eq_type, icon, half, row in skin.INV_WORN:
        slot = found[f'InvSlot{eq_type}']
        assert slot.tag == 'InvSlot' and number(slot, 'EQType') == eq_type
        assert box(slot) == (skin.LEFT + half * skin.HOT_PITCH // 2, skin.LEFT + row * skin.HOT_PITCH,
                             skin.HOT_SIZE, skin.HOT_SIZE)
        stock_x, stock_y = STOCK_WORN[eq_type]
        assert half == (stock_x - 120) // 20 and row == stock_y // 40 - (eq_type in raised), eq_type
        assert slot.findtext('Background') == f'TUI_HotSlot{icon}' and icon in skin.SLOT_ICONS
    for eq_type in skin.INV_BAG_TYPES:
        slot = found[f'InvSlot{eq_type}']
        assert number(slot, 'EQType') == eq_type and box(slot) == (0, 0, 0, 0)
        assert slot.findtext('Background') == 'TUI_Clear'
    # Every icon is drawn somewhere: the weapons' in the hot button window too, the rest only here.
    assert {icon for _, icon, _, _ in skin.INV_WORN} == set(skin.SLOT_ICONS)
    # The worn slots are mirrored about the doll's middle, on the hot bar's pitch, a padding apart; the doll starts a
    # padding from the window's edge. Legs and Feet, and the weapons, a padding apart and centered.
    boxes = {box(found[f'InvSlot{eq_type}']) for eq_type in range(1, 22)}
    doll_right = skin.LEFT + skin.INV_DOLL_WIDTH
    assert {(skin.LEFT + doll_right - x - w, y, w, h) for x, y, w, h in boxes} == boxes
    assert skin.BORDER + skin.LEFT == skin.PADDING and skin.HOT_PITCH == skin.HOT_SIZE + skin.PADDING
    assert max(y + h for _, y, _, h in boxes) == skin.LEFT + skin.INV_DOLL_HEIGHT
    assert max(x + w for x, _, w, _ in boxes) == doll_right
    legs, feet = box(found['InvSlot18']), box(found['InvSlot19'])
    assert feet[0] - (legs[0] + legs[2]) == skin.BUTTON_GAP
    weapons = sorted(box(found[f'InvSlot{t}']) for t in (13, 14, 11, 21))
    assert all(b[0] - (a[0] + a[2]) == skin.BUTTON_GAP for a, b in zip(weapons, weapons[1:]))
    assert weapons[0][1] - (legs[1] + legs[3]) == skin.BUTTON_ROW_GAP


def test_inventory_middle_is_where_a_dropped_item_is_equipped():
    # The stock drop area, see-through, over the middle a padding from every slot around it.
    _, _, found = inventory_parts()
    view = found['IW_CharacterView']
    assert view.tag == 'Screen' and view.findtext('TooltipReference') == 'Drop Item Here to Auto Equip'
    assert view.findtext('DrawTemplate') == skin.EDIT_TEMPLATE and view.findtext('Style_Border') == 'false'
    x, y, w, h = box(view)
    assert (x, y, w, h) == (skin.INV_MIDDLE_X, skin.INV_MIDDLE_TOP, skin.INV_MIDDLE_WIDTH, skin.INV_MIDDLE_HEIGHT)
    left, right, top, legs = (box(found[f'InvSlot{t}']) for t in (17, 8, 2, 18))
    assert x - (left[0] + left[2]) == right[0] - (x + w) == skin.PADDING
    assert y - (top[1] + top[3]) == legs[1] - (y + h) == skin.PADDING


def test_inventory_middle_shows_who_you_are_and_your_progress():
    # In the middle, the name, the level and class and the deity in the overlay's grey, lines stacked on their height,
    # then XP and AA (the user moved them here), each a caption, its % and its bar across the middle, the bar solid and
    # both in EverQuest's classic golden yellow (the user's picks). The first ink a padding under the top row, each
    # section two paddings under the digits or bar above, like the player window's sections. No HP: the player window
    # has it (the user).
    root, _, found = inventory_parts()
    name, level, cls, deity = (found[k] for k in ('NameLabel', 'LevelClassLabel', 'TUI_IW_Class', 'DeityLabel'))
    assert [number(e, 'EQType') for e in (name, level, cls, deity)] == [1, 2, 3, 4]
    assert rgb(name, 'TextColor') == rgb(level, 'TextColor') == rgb(cls, 'TextColor') == skin.TEXT_RGB
    assert rgb(deity, 'TextColor') == skin.PET_RGB
    top_row_bottom = skin.LEFT + skin.HOT_SIZE
    assert 0 <= box(name)[1] + skin.TEXT_INK_TOP - top_row_bottom - skin.PADDING < 1
    assert [box(e)[1] for e in (name, level, deity)] == [skin.INV_WHO_TOP + n * skin.TEXT_HEIGHT for n in range(3)]
    # The level right-aligned in two digits' room, the class a space after it.
    assert level.findtext('AlignRight') == 'true' and box(level)[2] == 2 * skin.DIGIT_WIDTH
    assert box(cls)[0] == box(level)[0] + box(level)[2] + skin.SPACE_WIDTH
    digits = skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT
    assert 0 <= skin.INV_XP_TOP + skin.TEXT_INK_TOP - (box(deity)[1] + digits) - 2 * skin.PADDING < 1
    bars = []
    for caption_id, caption, percent_type, gauge_id, gauge_type, top in skin.INV_PROGRESS:
        label, bar = found[caption_id or f'TUI_IW_{caption}Caption'], found[gauge_id or f'TUI_IW_{caption}Bar']
        assert label.findtext('Text') == caption and box(label)[:2] == (skin.INV_MIDDLE_X, top)
        assert number(bar, 'EQType') == gauge_type
        assert box(bar) == (skin.INV_MIDDLE_X, top + skin.BAR_TOP, skin.INV_MIDDLE_WIDTH, skin.BAR_HEIGHT)
        template = bar.find('GaugeDrawTemplate')
        assert (template.findtext('Fill'), template.findtext('Background')) == ('TUI_InvFill', 'TUI_InvTrack')
        assert rgb(bar, 'FillTint') == skin.GOLD_RGB
        percent = [e for e in root.iter('Label') if e.findtext('EQType') == str(percent_type)]
        assert len(percent) == 1 and rgb(percent[0], 'TextColor') == skin.GOLD_RGB
        sign = items(root, 'Gauge')[f'TUI_IW_{caption}PercentSign']
        assert rgb(sign, 'FillTint') == skin.GOLD_RGB
        assert box(percent[0])[0] + box(percent[0])[2] + skin.PERCENT_WIDTH == skin.INV_MIDDLE_RIGHT
        bars.append(box(bar))
    # XP keeps the stock ScreenIDs, which nothing looks up. The client looks up AltAdvLabel and AltAdvGauge and hid
    # them in game, so AA's caption and bar have none and show always (the user); the stock two stay, hidden.
    assert [(c, t) for c, _, t, g, e, _ in skin.INV_PROGRESS] == [('NextLevelLabel', 26), (None, 27)]
    assert [(g, e) for _, _, _, g, e, _ in skin.INV_PROGRESS] == [('ExpGauge', 4), (None, 5)]
    assert found['TUI_IW_AACaption'].find('ScreenID') is None and found['TUI_IW_AABar'].find('ScreenID') is None
    for screen_id in skin.INV_HIDDEN_AA:
        assert box(found[screen_id])[2:] == (0, 0)
    assert found['AltAdvGauge'].tag == 'Gauge' and number(found['AltAdvGauge'], 'EQType') == 5
    assert 0 <= skin.INV_AA_TOP + skin.TEXT_INK_TOP - (bars[0][1] + bars[0][3]) - 2 * skin.PADDING < 1
    # The AA bar a padding or more over Legs and Feet, inside the middle.
    assert bars[1][1] + bars[1][3] <= skin.INV_MIDDLE_TOP + skin.INV_MIDDLE_HEIGHT
    texts = [e for e in found.values() if e.tag == 'Label' and skin.INV_MIDDLE_X <= box(e)[0] < skin.INV_DIVIDER_X]
    assert len(texts) == 8  # name, level, class, deity, and each bar's caption and %
    assert all(box(e)[0] + box(e)[2] <= skin.INV_MIDDLE_RIGHT for e in texts)


def test_inventory_column_has_your_stats_numbers_and_coins():
    # Right of a divider a padding from the worn slots and from the column: the stats one to a line from the inside's
    # top (their ink 7.5px under the edge, like the bank window's names), then AC and ATK, then the weight (the user moved
    # them here), each under the row divider across the column (the user's request) a padding from the digits above and
    # from the next ink, the values in the game's green ending at the column's right; and the coin boxes stacked with the
    # last one level with the worn slots' bottom, as wide as the bank's so they share its art.
    root, window, found = inventory_parts()
    divider = box(found['TUI_IW_Divider'])
    assert divider == (skin.LEFT + skin.INV_DOLL_WIDTH + skin.PADDING, skin.LEFT, skin.DIVIDER_HEIGHT,
                       skin.INV_DOLL_HEIGHT)
    assert skin.INV_COLUMN_X == divider[0] + divider[2] + skin.PADDING
    assert box(window)[2] - 2 * skin.BORDER - skin.INV_RIGHT == skin.LEFT
    assert skin.BORDER + skin.INV_STATS_TOP + skin.TEXT_INK_TOP == 7.5
    lines = [(caption, eq_type, skin.INV_STATS_TOP + n * skin.TEXT_HEIGHT)
             for n, (caption, eq_type) in enumerate(skin.INV_STATS)]
    lines += [(caption, eq_type, skin.INV_NUMBERS_TOP + n * skin.TEXT_HEIGHT)
              for n, (caption, eq_type) in enumerate(skin.INV_NUMBERS)]
    for caption, eq_type, top in lines:
        label, value = found[f'{caption}Label'], found[f'{caption}NumberLabel']
        assert label.findtext('Text') == caption and box(label)[:2] == (skin.INV_COLUMN_X, top)
        assert number(value, 'EQType') == eq_type and value.findtext('AlignRight') == 'true'
        assert box(value)[1] == top and box(value)[0] + box(value)[2] == skin.INV_RIGHT
        assert rgb(value, 'TextColor') == skin.VALUE_RGB
    assert [eq_type for _, eq_type in skin.INV_STATS] == [5, 6, 8, 7, 9, 10, 11]  # STR STA AGI DEX WIS INT CHA
    assert skin.INV_NUMBERS == (('AC', 22), ('ATK', 23))
    weight = found['WeightLabel']
    assert weight.findtext('Text') == 'Weight' and box(weight)[:2] == (skin.INV_COLUMN_X, skin.INV_WEIGHT_TOP)
    # The weight's current and max each in room for three digits, right-aligned, so the max ends at the column's right
    # like the values above it (left-aligned in the player window's room for four, it stopped short: the user).
    current, slash, most = found['WeightNumberLabel'], found['TUI_IW_WeightSlash'], found['TUI_IW_WeightMax']
    assert (number(current, 'EQType'), number(most, 'EQType')) == (24, 25)
    assert box(current)[2] == box(most)[2] == skin.NUMBER_WIDTH
    assert current.findtext('AlignRight') == most.findtext('AlignRight') == 'true'
    assert box(current)[0] + box(current)[2] == box(slash)[0] and box(slash)[0] + box(slash)[2] == box(most)[0]
    assert box(most)[0] + box(most)[2] == skin.INV_RIGHT and slash.findtext('Text') == '/'
    assert rgb(current, 'TextColor') == rgb(most, 'TextColor') == skin.VALUE_RGB
    assert len({box(e)[1] for e in (weight, current, slash, most)}) == 1
    digits = skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT
    last_stat = lines[len(skin.INV_STATS) - 1][2]
    for (name, top), above, below in zip(skin.INV_COLUMN_DIVIDERS, (last_stat, lines[-1][2]),
                                         (skin.INV_NUMBERS_TOP, skin.INV_WEIGHT_TOP)):
        line = found[name]
        assert line.tag == 'StaticAnimation' and line.findtext('Animation') == 'TUI_InvDivider'
        assert box(line) == (skin.INV_COLUMN_X, top, skin.INV_COLUMN_WIDTH, skin.DIVIDER_HEIGHT)
        assert top - (above + digits) == skin.PADDING
        assert 0 <= below + skin.TEXT_INK_TOP - (top + skin.DIVIDER_HEIGHT) - skin.PADDING < 1
    assert [name for name, _ in skin.INV_COLUMN_DIVIDERS] == ['TUI_IW_StatsDivider', 'TUI_IW_NumbersDivider']
    anims = items(everything(), 'Ui2DAnimation')
    assert rect_of(anims['TUI_InvDivider'])[2:] == (skin.INV_COLUMN_WIDTH, 1)
    assert colors(anims['TUI_InvDivider']) == {skin.ROW_DIVIDER_RGBA}
    coins = [found[f'IW_Money{n}'] for n in range(4)]
    assert [box(c) for c in coins] == [
        (skin.INV_COLUMN_X, skin.INV_COINS_TOP + n * (skin.COIN_HEIGHT + skin.BUTTON_ROW_GAP), skin.INV_COLUMN_WIDTH,
         skin.COIN_HEIGHT) for n in range(4)]
    assert box(coins[-1])[1] + skin.COIN_HEIGHT == skin.LEFT + skin.INV_DOLL_HEIGHT
    assert box(coins[0])[1] - (skin.INV_WEIGHT_TOP + digits) >= skin.PADDING
    assert skin.INV_COLUMN_WIDTH == skin.BANK_COIN_WIDTH
    for coin, caption in zip(coins, skin.COIN_CAPTIONS):
        # Platinum to copper, as the stock decals show; no tooltips, as in the stock window.
        assert coin.find('TooltipReference') is None and coin.findtext('Text') == ''
        assert [(e.tag, e.text) for e in coin.find('ButtonDrawTemplate')] == [
            (state, f'TUI_BankCoin{skin.BUTTON_ART[state]}') for state in skin.BUTTON_STATES]
        check_coin_caption(root, window, coin, caption)


def test_inventory_buttons_fill_the_row_under_the_worn_slots():
    # Skills, AA, Destroy and Done a padding under the worn slots, filling the row a padding apart, the confirmation
    # dialog's kind with no tooltips (the stock ones have none), and the window's edge a padding under them.
    _, window, found = inventory_parts()
    buttons = [found[screen_id] for screen_id, _, _ in skin.INV_BUTTONS]
    assert [(s, n) for s, n, _ in skin.INV_BUTTONS] == [('IW_Skills', 'Skills'), ('IW_AltAdvBtn', 'AA'),
                                                        ('IW_Destroy', 'Destroy'), ('DoneButton', 'Done')]
    for button, (_, button_name, _) in zip(buttons, skin.INV_BUTTONS):
        check_confirmation_button(button, button_name)
        assert box(button)[1] == skin.LEFT + skin.INV_DOLL_HEIGHT + skin.BUTTON_ROW_GAP
    boxes = [box(b) for b in buttons]
    assert boxes[0][0] == skin.LEFT and boxes[-1][0] + boxes[-1][2] == skin.INV_RIGHT
    assert all(b[0] - (a[0] + a[2]) == skin.BUTTON_GAP for a, b in zip(boxes, boxes[1:]))
    assert max(w for *_, w, _ in boxes) - min(w for *_, w, _ in boxes) <= 1
    assert box(window)[3] - (skin.BORDER + boxes[0][1] + boxes[0][3]) == skin.PADDING


def test_inventory_hides_the_class_picture_hp_and_the_resists():
    # The client sets ClassAnim to the class's picture; with no size it shows nothing (the user didn't want it). The
    # client puts the picture into the animation ClassAnim names, so every control drawn with the same one showed it,
    # stretched (on TUI_Clear: the spell gems and the chat input, in game): its animation is its own. HP and the resists
    # are the player window's (the user); their stock labels stay, with no size and no text, and the max HP's, which has
    # no stock ScreenID, is left out.
    root, _, found = inventory_parts()
    picture = found['ClassAnim']
    assert picture.tag == 'StaticAnimation' and box(picture)[2:] == (0, 0)
    assert picture.findtext('Animation') == 'TUI_ClassAnim'
    assert len([e for e in everything().iter() if (e.text or '').strip() == 'TUI_ClassAnim']) == 1
    for screen_id in skin.INV_HIDDEN_LABELS:
        label = found[screen_id]
        assert label.tag == 'Label' and box(label)[2:] == (0, 0) and label.findtext('Text') == ''
        assert label.find('EQType') is None
    assert len(skin.INV_HIDDEN_LABELS) == 12 and {'HPLabel', 'HPNumberLabel'} <= set(skin.INV_HIDDEN_LABELS)
    assert not [e for e in root.iter('Label') if e.findtext('EQType') in ('17', '18')]


# The inspect window

STOCK_INSPECT = [*(f'InvSlot{n}' for n in range(1, 22)), 'INSW_Edit', 'DoneButton']


def inspect_parts():
    root, window = screen(skin.INSPECT_FILE)
    return root, window, {e.findtext('ScreenID') or e.get('item'): e for e in direct_pieces(root, window)}


def test_inspect_window_keeps_every_control_the_stock_one_has():
    # eqgame.exe looks up the message and Done, and Zeal finds the worn slots by their ScreenIDs to link an item
    # Alt+clicked, so each keeps its stock ID and EQType (8000 on). The game writes the player's name over the stock
    # title, in the window's font, centered across the bar; the bar holds the name alone (the user's pick: in a window
    # this narrow a longer name would run under the item window's Close), so Done closes it. A fixed size.
    root, window = check_inside_frame(skin.INSPECT_FILE, skin.INSPECT_WIDTH, bar=skin.INSPECT_TITLE_HEIGHT)
    assert window.get('item') == 'InspectWnd' and window.findtext('Text') == 'Inspect'
    assert window.findtext('TooltipReference') == 'Inspect'  # the stock window's
    assert window.findtext('Font') == str(skin.TEXT_FONT)
    assert window.findtext('Style_Closebox') == window.findtext('Style_Minimizebox') == 'false'
    assert window.findtext('Style_Sizable') == 'false' and window.findtext('DrawTemplate') == skin.INSPECT_TEMPLATE
    assert box(window)[2:] == (skin.INSPECT_WIDTH, skin.INSPECT_HEIGHT) == (216, 353)
    pieces = direct_pieces(root, window)
    ids = [e.findtext('ScreenID') for e in pieces if e.findtext('ScreenID')]
    assert sorted(ids) == sorted(STOCK_INSPECT) and len(set(ids)) == len(ids)
    _, _, found = inspect_parts()
    for n in range(1, 22):
        assert number(found[f'InvSlot{n}'], 'EQType') == skin.INSPECT_SLOT_TYPE + n == 8000 + n
    for folder in EQ_DIRS:
        path = Path(folder) / 'uifiles' / 'default' / skin.INSPECT_FILE
        if folder and path.is_file():
            stock = path.read_text(encoding='latin-1')
            assert sorted(re.findall(r'<ScreenID>\s*(\w+)\s*</ScreenID>', stock)) == sorted(STOCK_INSPECT)
            assert re.findall(r'<EQType>\s*(\d+)\s*</EQType>', stock) == [str(8000 + n) for n in range(1, 22)]
            break


def test_inspect_worn_slots_are_where_the_inventory_has_them():
    # The same squares and empty-slot icons as the inventory window's, in the same spots under the title bar, so their
    # gear sits where you see your own (the user's pick). The top row a padding under the bar's divider, where the
    # controls' inside starts, and the slots a padding from the window's sides.
    _, _, found = inspect_parts()
    _, _, inventory = inventory_parts()
    for eq_type, icon, *_ in skin.INV_WORN:
        slot, worn = found[f'InvSlot{eq_type}'], inventory[f'InvSlot{eq_type}']
        assert slot.tag == 'InvSlot'
        assert slot.findtext('Background') == worn.findtext('Background') == f'TUI_HotSlot{icon}'
        x, y, w, h = box(worn)
        assert box(slot) == (x, y - skin.LEFT + skin.INSPECT_DOLL_TOP, w, h)
    boxes = [box(found[f'InvSlot{n}']) for n in range(1, 22)]
    assert min(y for _, y, _, _ in boxes) == skin.INSPECT_DOLL_TOP == skin.PADDING
    assert skin.BORDER + min(x for x, *_ in boxes) == skin.PADDING
    assert skin.INSPECT_WIDTH - (skin.BORDER + max(x + w for x, _, w, _ in boxes)) == skin.PADDING


def test_inspect_title_bar_is_as_tall_as_the_name_needs():
    # The game writes the title (bar height - 14) // 2 - 1 down the bar (eqgame.exe, 0x5729b0), as the preview draws it.
    # The bar is the least height that puts its divider, the bottom row, a padding under the name's baseline (where
    # digits end); the name's ink then sits about 10.5px under the window's edge, where the game puts it.
    def text_top(height):
        return (height - skin.TEXT_HEIGHT) // 2 - 1

    def gap(height):  # clear rows from the name's baseline to the divider
        return height - skin.DIVIDER_HEIGHT - (text_top(height) + skin.INV_DIGITS_BOTTOM)

    height = skin.INSPECT_TITLE_HEIGHT
    assert gap(height) == skin.PADDING and all(gap(h) < skin.PADDING for h in range(skin.TEXT_HEIGHT, height))
    assert skin.BORDER + text_top(height) + skin.TEXT_INK_TOP == 10.5
    # The usual frame with the chat bar's look at that height, and the stock close box, which the window doesn't show.
    templates = items(everything(), 'WindowDrawTemplate')
    inspect, usual = templates[skin.INSPECT_TEMPLATE], templates[skin.FRAME_TEMPLATE]
    assert inspect.findtext('Background') == usual.findtext('Background') == skin.BACKGROUND_TEXTURE
    for part in ('Border', 'CloseBox'):
        assert [(e.tag, e.text) for e in inspect.find(part)] == [(e.tag, e.text) for e in usual.find(part)], part
    assert {inspect.findtext(f'Titlebar/{side}') for side in ('Left', 'Middle', 'Right')} == {'TUI_InspectTitleBar'}
    anims = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')
    bar = cut(decode(files()[skin.PIECES_TEXTURE]), anims['TUI_InspectTitleBar'])
    assert bar.size == (skin.TITLE_PIECE_WIDTH, height)
    rows = [set(bar.getpixel((x, y)) for x in range(bar.width)) for y in range(bar.height)]
    assert rows[:-1] == [{skin.PANEL_RGBA}] * (height - 1) and rows[-1] == {skin.TITLE_DIVIDER_RGBA}


def test_inspect_message_fills_the_middle_on_the_chat_inputs_strip():
    # The strip over the inventory's middle, a padding from every slot around it, drawn first. The message box draws
    # nothing itself: inset the field's padding at the sides and the bottom, its first line's ink about as far under the
    # strip's edge, in the text's color, wrapping from line to line with no scrollbar, like the stock box.
    root, window, found = inspect_parts()
    strip, message = found['TUI_INSW_Field'], found['INSW_Edit']
    pieces = direct_pieces(root, window)
    assert pieces.index(strip) + 1 == pieces.index(message)
    assert strip.tag == 'Screen' and strip.find('ScreenID') is None
    assert strip.findtext('DrawTemplate') == skin.FIELD_TEMPLATE and strip.findtext('Style_Border') == 'true'
    x, y, w, h = box(strip)
    assert (w, h) == (skin.INV_MIDDLE_WIDTH, skin.INV_MIDDLE_HEIGHT) == (120, 162)
    left, right, top, legs = (box(found[f'InvSlot{t}']) for t in (17, 8, 2, 18))
    assert x - (left[0] + left[2]) == right[0] - (x + w) == skin.PADDING
    assert y - (top[1] + top[3]) == legs[1] - (y + h) == skin.PADDING
    assert message.tag == 'Editbox' and message.findtext('Style_Multiline') == 'true'
    assert message.findtext('DrawTemplate') == skin.EDIT_TEMPLATE and message.find('Style_VScroll') is None
    assert message.findtext('Style_Transparent') == 'true' and message.findtext('Style_Border') == 'false'
    assert message.findtext('Font') == str(skin.TEXT_FONT) and rgb(message, 'TextColor') == skin.TEXT_RGB
    mx, my, mw, mh = box(message)
    assert mx - x == (x + w) - (mx + mw) == (y + h) - (my + mh) == skin.FIELD_PADDING
    assert abs(my - y + skin.TEXT_INK_TOP - skin.FIELD_PADDING) <= 0.5


def test_inspect_done_fills_the_row_under_the_worn_slots():
    # The confirmation dialog's kind, with no tooltip (the stock one has none), a padding under the worn slots and
    # across them, and the window's edge a padding under it.
    _, window, found = inspect_parts()
    done = found['DoneButton']
    check_confirmation_button(done, 'Done')
    x, y, w, h = box(done)
    assert y - max(box(found[f'InvSlot{n}'])[1] + skin.HOT_SIZE for n in range(1, 22)) == skin.BUTTON_ROW_GAP
    assert (x, w) == (skin.LEFT, skin.INV_DOLL_WIDTH)
    assert box(window)[3] - (skin.BORDER + skin.INSPECT_TITLE_HEIGHT + y + h) == skin.PADDING


# The tracking window

# Every control of the stock window, (tag, ScreenID), in the order ours draws them.
STOCK_TRACKING = [
    ('Button', 'TRW_FilterRedButton'), ('Button', 'TRW_FilterYellowButton'), ('Button', 'TRW_FilterWhiteButton'),
    ('Button', 'TRW_FilterBlueButton'), ('Button', 'TRW_FilterLightBlueButton'), ('Button', 'TRW_FilterGreenButton'),
    ('Listbox', 'TRW_TrackingList'), ('Label', 'TRW_TrackSortLabel'), ('Label', 'TRW_TrackPlayersLabel'),
    ('Button', 'TRW_TrackButton'), ('Button', 'DoneButton'), ('Combobox', 'TRW_TrackPlayersCombobox'),
    ('Combobox', 'TRW_TrackSortCombobox'), ('Label', 'TRW_FiltersLabel'),
]


def tracking_parts():
    root, window = screen(skin.TRACKING_FILE)
    return root, window, {e.findtext('ScreenID'): e for e in direct_pieces(root, window)}


def test_tracking_window_keeps_every_control_the_stock_one_has():
    # A fixed size with no title bar or close box (the user's pick), so it drags by its background and Cancel closes it;
    # as wide as the hot button window. The dropdowns come last, as in the stock window, so an open one lies over the
    # rest, Sort's over the Players box.
    root, window = check_inside_frame(skin.TRACKING_FILE, skin.TRACK_WIDTH)
    assert window.get('item') == 'TrackingWnd' and window.findtext('Text') == 'Tracking'
    assert window.findtext('Style_Sizable') == window.findtext('Style_Closebox') == 'false'
    assert window.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    assert box(window)[2:] == (skin.TRACK_WIDTH, skin.TRACK_HEIGHT) == (skin.HOT_WIDTH, 451)
    assert [(e.tag, e.findtext('ScreenID')) for e in direct_pieces(root, window)] == STOCK_TRACKING
    for folder in EQ_DIRS:
        path = Path(folder) / 'uifiles' / 'default' / skin.TRACKING_FILE
        if folder and path.is_file():
            stock = re.findall(r'<(\w+) item\s*=\s*"[^"]*">\s*<ScreenID>(\w+)</ScreenID>',
                               path.read_text(encoding='latin-1'))
            assert sorted(stock) == sorted(STOCK_TRACKING)
            break


def test_tracking_filters_are_con_color_squares_filling_the_top_row():
    # Six checkboxes a padding apart filling the content row in the stock order, each showing a square of its con color
    # (the user's pick), the stock letters' colors, and naming it in its tooltip in eqstr_en.txt's words for
    # /trackfilter ("You will see %1 NPCs when tracking").
    _, _, found = tracking_parts()
    assert [rgb_ for *_, rgb_ in skin.TRACK_FILTERS] == [(240, 0, 0), (240, 240, 0), (240, 240, 240), (0, 0, 240),
                                                         (0, 240, 240), (0, 240, 0)]
    boxes = []
    for screen_id, color_name, tooltip, _ in skin.TRACK_FILTERS:
        button = found[screen_id]
        assert button.findtext('Style_Checkbox') == 'true' and button.findtext('TooltipReference') == tooltip
        assert tooltip.endswith(' NPCs')
        assert {state: button.findtext(f'ButtonDrawTemplate/{state}') for state in skin.BUTTON_STATES} == {
            state: f'TUI_Filter{color_name}{skin.TOGGLE_ART[state]}' for state in skin.BUTTON_STATES}
        boxes.append(box(button))
    assert all(b[1] == skin.FILTER_TOP and b[2:] == (skin.FILTER_SIZE, skin.FILTER_SIZE) == (22, 22) for b in boxes)
    assert boxes[0][0] == skin.LEFT and boxes[-1][0] + boxes[-1][2] == skin.TRACK_RIGHT
    assert all(b[0] - (a[0] + a[2]) == skin.BUTTON_GAP for a, b in zip(boxes, boxes[1:]))


def test_tracking_filter_squares_are_bright_while_listed_and_dim_while_filtered_out():
    # Each state's art is the selector toggle's look at the filter's size, with the con color's square in its middle:
    # the color itself while pressed, faint while not.
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')
    size, low = skin.FILTER_SIZE, (skin.FILTER_SIZE - skin.FILTER_SWATCH) // 2
    middle = size // 2
    for _, color_name, _, con in skin.TRACK_FILTERS:
        for state, (fill, edge, _) in skin.TOGGLE_LOOKS.items():
            art = cut(atlas, anims[f'TUI_Filter{color_name}{state}'])
            toggle = as_image(skin.snapped_art(skin.panel_texture(size, size, fill, edge)))
            assert art.size == toggle.size == (size, size)
            outside = [(x, y) for x in range(size) for y in range(size)
                       if not (low - 1 <= x <= low + skin.FILTER_SWATCH and low - 1 <= y <= low + skin.FILTER_SWATCH)]
            assert all(art.getpixel(spot) == toggle.getpixel(spot) for spot in outside), (color_name, state)
            center = art.getpixel((middle, middle))
            if state.startswith('Pressed'):
                assert center == skin.snapped((*con, 255))
                # The square's middle row is the color edge to edge, FILTER_SWATCH wide.
                row = [x for x in range(size) if art.getpixel((x, middle)) == center]
                assert row == list(range(low, low + skin.FILTER_SWATCH))
            elif state == 'Normal':
                assert center[3] < 128 and center != skin.snapped((*con, 255))


def test_tracking_dropdowns_sit_by_their_captions():
    # Sort and Players, the stock controls, each box from a padding after its caption to the window's padding, filled
    # by the client with /tracksort's five choices and /trackplayers' three (eqstr_en.txt 13140-13154): the open list
    # is as tall as they are, and the file gives it no choices of its own.
    _, _, found = tracking_parts()
    assert [(caption, choices) for _, caption, _, _, choices in skin.TRACK_COMBOS] == [('Sort', 5), ('Players', 3)]
    for caption_id, caption, combo_id, top, choices in skin.TRACK_COMBOS:
        combo, label = found[combo_id], found[caption_id]
        assert box(combo) == (skin.TRACK_COMBO_X, top, skin.TRACK_COMBO_WIDTH, skin.COMBO_HEIGHT)
        assert skin.TRACK_COMBO_X + skin.TRACK_COMBO_WIDTH == skin.TRACK_RIGHT
        assert combo.findtext('DrawTemplate') == skin.COMBO_TEMPLATE and combo.findtext('Button') == skin.COMBO_BUTTON
        assert combo.findtext('Style_Border') == 'true' and combo.find('Choices') is None
        assert number(combo, 'ListHeight') == choices * skin.COMBO_ROW_HEIGHT + 2
        assert combo.findtext('Font') == str(skin.TEXT_FONT) and rgb(combo, 'TextColor') == skin.TEXT_RGB
        assert label.findtext('Text') == caption and label.findtext('Font') == str(skin.TEXT_FONT)
        assert rgb(label, 'TextColor') == skin.CAPTION_RGB and label.find('EQType') is None
        assert box(label) == (skin.LEFT, top + skin.TRACK_CAPTION_DROP, skin.TRACK_CAPTION_WIDTH, skin.TEXT_HEIGHT)


def test_tracking_dropdowns_have_only_what_the_stock_schema_gives_a_combobox():
    types = stock_sidl()
    allowed = {name for kind in ('ScreenPiece', 'Control', 'Combobox')
               for name in re.findall(r'<element name\s*=\s*"(\w+)"', types[kind])}
    assert {'Button', 'ListHeight', 'DrawTemplate', 'TextColor'} <= allowed
    _, _, found = tracking_parts()
    for _, _, combo_id, _, _ in skin.TRACK_COMBOS:
        assert {child.tag for child in found[combo_id]} <= allowed


def test_dropdowns_are_the_panel_in_a_thin_outline_with_the_scrollbars_chevron():
    # The box and its open list: the panel's own background, opaque so an open list covers the list under it, in a 1px
    # outline of the window edge's color, like the chat input's. The arrow is the scrollbar's down chevron, centered
    # down the box's inside.
    root = parse(skin.ANIMATIONS_FILE)
    anims = items(root, 'Ui2DAnimation')
    template = items(root, 'WindowDrawTemplate')[skin.COMBO_TEMPLATE]
    assert template.findtext('Background') == skin.BACKGROUND_TEXTURE
    assert set(pixels(decode(files()[skin.BACKGROUND_TEXTURE]))) == {skin.PANEL_RGBA} and skin.PANEL_RGBA[3] == 255
    sides = {side.text for side in template.find('Border') if not side.tag.startswith('Overlap')}
    assert sides == {'TUI_FieldEdge'} and colors(anims['TUI_FieldEdge']) == {skin.EDGE_FADED}
    assert rect_of(anims['TUI_FieldEdge'])[2:] == (1, 1)
    atlas = decode(files()[skin.PIECES_TEXTURE])
    arrow = items(root, 'ButtonDrawTemplate')[skin.COMBO_BUTTON]
    assert skin.COMBO_ARROW_HEIGHT == skin.COMBO_HEIGHT - 2
    shift = (skin.COMBO_ARROW_HEIGHT - skin.SCROLL_BUTTON_HEIGHT) // 2
    for state in skin.BUTTON_STATES:
        look = skin.BUTTON_ART[state]
        assert arrow.findtext(state) == f'TUI_ComboDown{look}'
        art = cut(atlas, anims[f'TUI_ComboDown{look}'])
        scroll = cut(atlas, anims[f'TUI_ScrollDown{look}'])
        assert art.size == (skin.SCROLL_WIDTH, skin.COMBO_ARROW_HEIGHT)
        assert pixels(art.crop((0, shift, skin.SCROLL_WIDTH, shift + skin.SCROLL_BUTTON_HEIGHT))) == pixels(scroll)
        rest = pixels(art.crop((0, 0, skin.SCROLL_WIDTH, shift))) + pixels(
            art.crop((0, shift + skin.SCROLL_BUTTON_HEIGHT, skin.SCROLL_WIDTH, skin.COMBO_ARROW_HEIGHT)))
        assert all(p[3] == 0 for p in rest)


def test_tracking_list_is_one_column_of_names_with_no_heading():
    # The stock list's one column, 150px, and our scrollbar fill the content row, 24 names tall (the user's pick). Like
    # the stock list it has no heading, so no heading strip either.
    _, _, found = tracking_parts()
    listbox = found['TRW_TrackingList']
    [column] = listbox.findall('Columns')
    assert column.find('Header') is None and not column.findtext('Heading')
    assert number(column, 'Width') == 150 == skin.TRACK_CONTENT_WIDTH - skin.SCROLL_WIDTH
    x, y, width, height = box(listbox)
    assert (x, width) == (skin.LEFT, skin.TRACK_CONTENT_WIDTH)
    assert height == skin.TRACK_ROWS * skin.TEXT_HEIGHT and skin.TRACK_ROWS == 24
    assert listbox.findtext('DrawTemplate') == skin.EDIT_TEMPLATE
    assert listbox.findtext('Style_VScroll') == 'true' and listbox.findtext('Style_Border') == 'false'
    assert listbox.findtext('Font') == str(skin.TEXT_FONT) and rgb(listbox, 'TextColor') == skin.TEXT_RGB
    assert listbox.find('TooltipReference') is None


def test_tracking_window_follows_the_spacing_standard():
    _, window, found = tracking_parts()
    b, width = skin.BORDER, box(window)[2]
    filters = [box(found[screen_id]) for screen_id, *_ in skin.TRACK_FILTERS]
    sort, players = box(found['TRW_TrackSortCombobox']), box(found['TRW_TrackPlayersCombobox'])
    names = box(found['TRW_TrackingList'])
    track, cancel = box(found['TRW_TrackButton']), box(found['DoneButton'])
    # The filters a padding from the window's edge, across and down, the row ending a padding from the right edge.
    assert b + filters[0][0] == b + filters[0][1] == skin.PADDING
    assert width - (b + filters[-1][0] + filters[-1][2]) == skin.PADDING
    # Each dropdown a padding under what's above it, ending a padding from the window's edge.
    assert sort[1] - (filters[0][1] + filters[0][3]) == skin.PADDING
    assert players[1] - (sort[1] + sort[3]) == skin.PADDING
    assert all(width - (b + combo[0] + combo[2]) == skin.PADDING for combo in (sort, players))
    # Each caption a padding from the window's edge and from its box ("Players" fills its label: 41px in Arial 12), its
    # ink's middle level with the box's, as the Actions window's page number between its arrows.
    for caption_id, _, combo_id, _, _ in skin.TRACK_COMBOS:
        caption, combo = box(found[caption_id]), box(found[combo_id])
        assert b + caption[0] == skin.PADDING and combo[0] - (caption[0] + caption[2]) == skin.PADDING
        assert abs(caption[1] + skin.DIGITS_INK_MIDDLE - (combo[1] + combo[3] / 2)) <= 0.5
    # The list has no heading row, so its first name's ink, TEXT_INK_TOP into its line, a padding under the Players box
    # (rounded up to a whole pixel).
    gap = names[1] - (players[1] + players[3])
    assert gap == skin.DIVIDER_TO_NAME and gap - 1 < skin.PADDING - skin.TEXT_INK_TOP <= gap
    # Track and Cancel a padding under the list, filling the row a padding apart, and the window's edge a padding under.
    assert track[1] == cancel[1] == names[1] + names[3] + skin.BUTTON_ROW_GAP
    assert track[0] == skin.LEFT and cancel[0] - (track[0] + track[2]) == skin.BUTTON_GAP
    assert cancel[0] + cancel[2] == skin.TRACK_RIGHT and track[2] == cancel[2]
    assert box(window)[3] - (b + track[1] + track[3]) == skin.PADDING


def test_tracking_buttons_are_the_confirmation_dialogs_kind_with_the_stock_words():
    # Cancel is the stock DoneButton, which closes the window; neither has a tooltip (the stock ones have none). The
    # "Filters" caption is there for the client, with no size and no text.
    _, _, found = tracking_parts()
    check_confirmation_button(found['TRW_TrackButton'], 'Track')
    check_confirmation_button(found['DoneButton'], 'Cancel')
    hidden = found['TRW_FiltersLabel']
    assert box(hidden)[2:] == (0, 0) and hidden.findtext('Text') == ''


# The Alternate Advancement window

# Every ScreenID of the stock window. eqgame.exe looks up all but the three captions and the bar, which works by its
# EQType.
STOCK_AA = ['TrainButton', 'HotButton', 'DoneButton', 'LessExpButton', 'MoreExpButton', 'PercentLabel', 'ExpCount',
            'ExpGauge', 'TotalLabel', 'CurrentLabel', 'TotalCount', 'CurrentCount', 'Description',
            *[f'{kind}{n}' for n in range(1, 6) for kind in ('List', 'Page')], 'Subwindows', 'Timer']


def aa_parts():
    """The AA window file, its window, and every control in the file by ScreenID (or item, where it has none)."""
    root, window = screen(skin.AA_FILE)
    return root, window, {e.findtext('ScreenID') or e.get('item'): e for e in root if e.get('item')}


def aa_tabs():
    root, window, found = aa_parts()
    tabs = found['Subwindows']
    return root, window, tabs, [items(root, 'Page')[p.text] for p in tabs.findall('Pages')]


def test_aa_window_keeps_every_control_the_stock_one_has():
    # A fixed size with no title bar or close box (the user's pick), so it drags by its background and Done closes it.
    # Every stock control is there under its ScreenID, each the client looks up of the stock kind; the stock captions,
    # which nothing looks up, are ours.
    root, window = check_inside_frame(skin.AA_FILE, skin.AA_WIDTH)
    assert window.get('item') == 'AAWindow' and window.findtext('Text') == 'Alternate Advancement Window'
    assert window.findtext('Style_Sizable') == window.findtext('Style_Closebox') == 'false'
    assert window.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    assert box(window)[2:] == (skin.AA_WIDTH, skin.AA_HEIGHT) == (549, 414)
    ids = [e.findtext('ScreenID') for e in root if e.findtext('ScreenID')]
    assert sorted(ids) == sorted(STOCK_AA) and len(set(ids)) == len(ids)
    _, _, found = aa_parts()
    kinds = {'Subwindows': 'TabBox', 'Description': 'STMLbox', 'ExpCount': 'StaticText', 'CurrentCount': 'StaticText',
             'TotalCount': 'StaticText', 'Timer': 'Label', 'ExpGauge': 'Gauge',
             **{f'Page{n}': 'Page' for n in range(1, 6)}, **{f'List{n}': 'Listbox' for n in range(1, 6)},
             **{b: 'Button' for b in ('TrainButton', 'HotButton', 'DoneButton', 'LessExpButton', 'MoreExpButton')}}
    assert {screen_id: found[screen_id].tag for screen_id in kinds} == kinds
    for folder in EQ_DIRS:
        path = Path(folder) / 'uifiles' / 'default' / skin.AA_FILE
        if folder and path.is_file():
            stock = re.findall(r'<ScreenID>\s*(\w+)\s*</ScreenID>', path.read_text(encoding='latin-1'))
            assert sorted(stock) == sorted(STOCK_AA)
            break


def test_aa_tabs_are_the_stock_pages_with_their_names_on_them():
    # The stock pages in the stock order, each holding only its list, in a tab box with the Actions window's tab and page
    # border templates (see PAGE_RIGHT). Each tab is the Actions tabs' toggle with no icon and the page's name painted on
    # (where the tab box would write its own TabText isn't known) in the icons' color, dimmer while closed, centered;
    # the open tab lit.
    root, _, tabs, pages = aa_tabs()
    defined = {e.get('item'): e for e in root}
    assert (tabs.findtext('TabBorderTemplate'), tabs.findtext('PageBorderTemplate')) == (skin.TAB_BORDER,
                                                                                          skin.PAGE_BORDER)
    assert [p.findtext('ScreenID') for p in pages] == [f'Page{n}' for n in range(1, 6)]
    assert [[defined[piece.text].findtext('ScreenID') for piece in p.findall('Pieces')] for p in pages] == [
        [f'List{n}'] for n in range(1, 6)]
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(everything(), 'Ui2DAnimation')
    for page, (_, _, name, art), width in zip(pages, skin.AA_PAGES, skin.AA_TAB_WIDTHS):
        assert page.find('TabText') is None and page.find('TooltipReference') is None
        assert (page.findtext('TabIcon'), page.findtext('TabIconActive')) == (f'TUI_Tab{art}Normal',
                                                                              f'TUI_Tab{art}Pressed')
        assert page.findtext('Style_Transparent') == 'true' and page.findtext('Style_Border') == 'false'
        (left, top), ink = skin.TAB_INK[name]
        assert {len(row) for row in ink} == {len(ink[0])} and abs(left + len(ink[0]) / 2 - width / 2) <= 0.5
        lit = {}
        for state, shift in (('Normal', 0), ('Pressed', skin.TAB_SHIFT)):
            # Closed at the top of its art, open TAB_SHIFT lower (the client draws a closed page's tab that much
            # lower), clear around it.
            full = cut(atlas, anims[f'TUI_Tab{art}{state}'])
            assert full.size == (width, skin.TAB_ART_HEIGHT)
            tab = full.crop((0, shift, width, shift + skin.TOGGLE_SIZE))
            plain = as_image(skin.toggle_art((), state, width, skin.TOGGLE_SIZE))
            name_color = (*skin.ICON_RGB, skin.ICON_LOOKS[state][2])
            for y in range(tab.height):
                for x in range(tab.width):
                    inked = 0 <= y - top < len(ink) and 0 <= x - left < len(ink[0])
                    coverage = int(ink[y - top][x - left], 16) / 15 if inked else 0
                    expected = skin.snapped(skin.over(name_color, coverage, plain.getpixel((x, y))))
                    assert tab.getpixel((x, y)) == expected, (name, state, x, y)
            full.paste((0, 0, 0, 0), (0, shift, width, shift + skin.TOGGLE_SIZE))
            assert {p[3] for p in pixels(full)} == {0}
            lit[state] = sum(sum(p[:3]) * p[3] for p in pixels(tab))
        assert lit['Pressed'] > lit['Normal'], name
    assert [name for _, _, name, _ in skin.AA_PAGES] == ['General', 'Archetype', 'Class', 'PoP Advance', 'PoP Ability']


def test_aa_tabs_and_lists_follow_the_spacing_standard():
    _, _, tabs, pages = aa_tabs()
    _, _, found = aa_parts()
    assert box(tabs) == (0, 0, skin.AA_TAB_BOX_WIDTH, skin.AA_TAB_BOX_HEIGHT)
    spots, cut_at, (left, top, right, bottom) = tab_box_layout(tabs, pages)
    toggles = [(x, y + skin.TAB_SHIFT) for x, y in spots]
    edges = [(skin.BORDER + x, skin.BORDER + x + w) for (x, _), w in zip(toggles, skin.AA_TAB_WIDTHS)]
    # The tabs a padding apart from the window's padding to the list's right edge, each as wide ("PoP Advance" in font 2
    # and a padding either side), all level, a pixel lower than the padding like the Actions window's (see TAB_TOP).
    assert edges[0][0] == skin.PADDING and edges[-1][1] == skin.BORDER + skin.LEFT + skin.AA_LIST_WIDTH
    assert [b[0] - a[1] for a, b in zip(edges, edges[1:])] == [skin.PADDING] * (len(edges) - 1)
    assert skin.AA_TAB_WIDTHS == [64 + 2 * skin.PADDING] * 5
    assert [skin.BORDER + x for x in skin.AA_TAB_LEFTS] == [edge[0] for edge in edges]
    assert {skin.BORDER + y for _, y in toggles} == {skin.PADDING + 1}
    assert toggles[0][1] + skin.TOGGLE_SIZE <= cut_at  # a closed tab is never cut off
    # Under the tabs, the row divider across the list's width, a padding from the tabs and from the page, which the tab
    # box puts a padding in from the window's left; each list fills its page.
    divider = found['TUI_AAW_TabDivider']
    dx, dy, dw, dh = box(divider)
    assert divider.findtext('Animation') == 'TUI_AADivider'
    assert (skin.BORDER + dx, dw, dh) == (skin.PADDING, skin.AA_LIST_WIDTH, 1)
    assert dy - (toggles[0][1] + skin.TOGGLE_SIZE) == skin.PADDING and top - (dy + dh) == skin.PADDING
    assert (left, right - left, bottom - top) == (skin.LEFT, skin.AA_LIST_WIDTH, skin.AA_LIST_HEIGHT)
    for n in range(1, 6):
        assert box(found[f'List{n}']) == (0, 0, skin.AA_LIST_WIDTH, skin.AA_LIST_HEIGHT)
    # The tab box ends where the divider beside the list stands: past the list it holds only clear space.
    assert box(tabs)[2] == box(found['TUI_AAW_Divider'])[0]
    anims = items(everything(), 'Ui2DAnimation')
    assert rect_of(anims['TUI_AADivider'])[2:] == (skin.AA_LIST_WIDTH, 1)
    assert colors(anims['TUI_AADivider']) == {skin.ROW_DIVIDER_RGBA}


def test_aa_lists_show_each_ability_its_rank_and_cost():
    # The client's three columns in its order, each heading on the strip: the rank and cost each their widest text in
    # font 3 (Arial 12px) and a padding ("10/10" and "Cost"), the names the rest. Straight on the window's panel with the
    # slim scrollbar, in the windows' font, 18 rows under the heading (the user's pick), no tooltip (the stock lists have
    # none).
    _, _, found = aa_parts()
    for n in range(1, 6):
        listbox = found[f'List{n}']
        columns = listbox.findall('Columns')
        assert [c.findtext('Heading') for c in columns] == ['Ability', 'Rank', 'Cost']
        assert all(c.findtext('Header') == skin.LIST_HEADER for c in columns)
        widths = [number(c, 'Width') for c in columns]
        assert widths == [324, 31 + skin.PADDING, 25 + skin.PADDING]
        assert sum(widths) + skin.SCROLL_WIDTH == box(listbox)[2] == skin.AA_LIST_WIDTH
        assert box(listbox)[3] == skin.RAID_HEADER_HEIGHT + 18 * skin.TEXT_HEIGHT and skin.AA_ROWS == 18
        assert listbox.findtext('DrawTemplate') == skin.EDIT_TEMPLATE
        assert listbox.findtext('Style_VScroll') == 'true' and listbox.findtext('Style_Border') == 'false'
        assert listbox.findtext('Font') == str(skin.TEXT_FONT) and rgb(listbox, 'TextColor') == skin.TEXT_RGB
        assert listbox.find('TooltipReference') is None


def test_aa_description_is_under_the_list_straight_on_the_panel():
    # The row divider a padding under the list, the first line's ink a padding under it (rounded up to a whole pixel),
    # six lines as wide as the list, and the window's edge a padding under them. Like the item window's text: our slim
    # scrollbar, nothing of its own drawn, in the windows' font.
    _, window, found = aa_parts()
    text, line = found['Description'], found['TUI_AAW_ListDivider']
    x, y, w, h = box(text)
    assert (x, w, h) == (skin.LEFT, skin.AA_LIST_WIDTH, 6 * skin.TEXT_HEIGHT)
    assert text.findtext('DrawTemplate') == skin.EDIT_TEMPLATE and text.findtext('Font') == str(skin.TEXT_FONT)
    assert text.findtext('Style_VScroll') == 'true' and text.findtext('Style_HScroll') == 'false'
    assert text.findtext('Style_Transparent') == 'true' and text.findtext('Style_Border') == 'false'
    assert line.findtext('Animation') == 'TUI_AADivider'
    assert box(line) == (skin.LEFT, skin.PAGE_TOP + skin.AA_LIST_HEIGHT + skin.PADDING, skin.AA_LIST_WIDTH, 1)
    gap = y - (box(line)[1] + 1)
    assert gap == skin.DIVIDER_TO_NAME and gap - 1 < skin.PADDING - skin.TEXT_INK_TOP <= gap
    assert box(window)[3] - (skin.BORDER + y + h) == skin.PADDING


def test_aa_column_has_your_points_the_split_the_reuse_timer_and_the_buttons():
    root, window, found = aa_parts()
    b, x = skin.BORDER, skin.AA_COLUMN_X
    # The divider standing a padding from the list and from the column, from the top padding to the bottom one; the
    # column three slots wide, like the inventory's, a padding from the window's right edge.
    divider = box(found['TUI_AAW_Divider'])
    assert divider == (skin.LEFT + skin.AA_LIST_WIDTH + skin.PADDING, skin.LEFT, 1, skin.AA_BOTTOM - skin.LEFT)
    assert x == divider[0] + 1 + skin.PADDING and box(window)[2] - (b + skin.AA_RIGHT) == skin.PADDING
    assert b + divider[1] == skin.PADDING and box(window)[3] - (b + divider[1] + divider[3]) == skin.PADDING
    assert skin.AA_COLUMN_WIDTH == 3 * skin.HOT_SIZE + 2 * skin.PADDING == skin.INV_MIDDLE_WIDTH
    # No AA XP line (the inventory shows it): the stock bar kept, hidden, and no caption or % of ours.
    bar = found['ExpGauge']
    assert bar.tag == 'Gauge' and number(bar, 'EQType') == 5 and box(bar)[2:] == (0, 0)
    assert bar.findtext('GaugeDrawTemplate/Fill') == 'TUI_Clear'
    assert not [e for e in root.iter('Label') if e.findtext('EQType') == '27']
    assert not {'TUI_AAW_XPCaption', 'TUI_AAW_XPPercent', 'TUI_AAW_XPPercentSign'} & {e.get('item') for e in root}
    # Your points spent and available at the inside's top, like the inventory's stats (the first line's ink 7.5px under
    # the edge), stacked on their line height, each value a StaticText as in the stock window, right-aligned in the
    # game's green ending at the column's right. The items are named by the stock captions' ScreenIDs.
    assert skin.AA_NUMBERS == (('TotalLabel', 'Spent', 'TotalCount'), ('CurrentLabel', 'Available', 'CurrentCount'))
    assert skin.AA_NUMBERS_TOP == 0 and b + skin.AA_NUMBERS_TOP + skin.TEXT_INK_TOP == 7.5
    for n, (caption_id, caption, value_id) in enumerate(skin.AA_NUMBERS):
        top = skin.AA_NUMBERS_TOP + n * skin.TEXT_HEIGHT
        label, value = found[caption_id], found[value_id]
        assert label.get('item') == f'TUI_AAW_{caption_id}'
        assert label.findtext('Text') == caption and box(label)[:2] == (x, top)
        assert box(label)[0] + box(label)[2] == box(value)[0]
        assert value.tag == 'StaticText' and value.find('EQType') is None
        assert box(value) == (skin.AA_RIGHT - skin.AA_VALUE_WIDTH, top, skin.AA_VALUE_WIDTH, skin.TEXT_HEIGHT)
        assert value.findtext('AlignRight') == 'true' and rgb(value, 'TextColor') == skin.VALUE_RGB
    assert not [e for e in root.iter('Label') if e.findtext('Text') == 'Points']
    # Each section set apart by the inventory column's divider across the column, a padding under the counts' digits
    # and under the - and + row's outline, and a padding over the next caption's ink, like the inventory's stats.
    digits = skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT
    row = skin.AA_SPLIT_ROW_TOP
    assert skin.AA_COLUMN_WIDTH == skin.INV_COLUMN_WIDTH
    assert [name for name, _ in skin.AA_COLUMN_DIVIDERS] == ['TUI_AAW_PointsDivider', 'TUI_AAW_SplitDivider']
    for (name, line_top), above, below in zip(skin.AA_COLUMN_DIVIDERS, (top + digits, row + skin.ARROW_SIZE),
                                              (skin.AA_SPLIT_TOP, skin.AA_TIMER_TOP)):
        line = found[name]
        assert line.tag == 'StaticAnimation' and line.findtext('Animation') == 'TUI_InvDivider'
        assert box(line) == (x, line_top, skin.AA_COLUMN_WIDTH, skin.DIVIDER_HEIGHT)
        assert line_top - above == skin.PADDING
        assert 0 <= below + skin.TEXT_INK_TOP - (line_top + skin.DIVIDER_HEIGHT) - skin.PADDING < 1
    # How much of your XP goes to AA: a padding under the caption's ink the row of - and + at the column's ends, the
    # social page arrows' size, with the client's % between them a padding from each, its digits' ink centered on them,
    # in the game's green.
    split = found['PercentLabel']
    assert split.findtext('Text') == 'XP to AA' and box(split)[:2] == (x, skin.AA_SPLIT_TOP)
    assert row - (skin.AA_SPLIT_TOP + skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT) == skin.PADDING
    less, more, count = found['LessExpButton'], found['MoreExpButton'], found['ExpCount']
    size = (skin.ARROW_SIZE, skin.ARROW_SIZE)
    assert box(less) == (x, row, *size) and box(more) == (skin.AA_RIGHT - skin.ARROW_SIZE, row, *size)
    for button, icon in ((less, 'Minus'), (more, 'Plus')):
        assert [(e.tag, e.text) for e in button.find('ButtonDrawTemplate')] == [
            (state, f'TUI_Toggle{icon}{skin.ICON_ART[state]}') for state in skin.BUTTON_STATES]
        assert button.find('TooltipReference') is None and button.findtext('Style_Checkbox') == 'false'
    cx, cy, cw, ch = box(count)
    assert cx - (x + skin.ARROW_SIZE) == skin.PADDING and box(more)[0] - (cx + cw) == skin.PADDING
    assert count.findtext('AlignCenter') == 'true' and rgb(count, 'TextColor') == skin.VALUE_RGB
    assert cy - row + skin.DIGITS_INK_MIDDLE == skin.ARROW_SIZE / 2 and ch == skin.TEXT_HEIGHT
    # The selected ability's reuse timer (the user's call: it matters) on the line under its caption, stacked on their
    # line height: the client's Timer, a label as in the stock window, right-aligned across the column in the game's
    # green like the counts.
    caption, timer = found['TUI_AAW_TimerLabel'], found['Timer']
    assert skin.AA_TIMER_CAPTION == 'Ability ready in:' and caption.findtext('Text') == skin.AA_TIMER_CAPTION
    assert caption.find('ScreenID') is None and box(caption) == (x, skin.AA_TIMER_TOP, skin.AA_COLUMN_WIDTH,
                                                                  skin.TEXT_HEIGHT)
    assert timer.tag == 'Label' and timer.find('EQType') is None and timer.findtext('Text') == ''
    assert box(timer) == (x, skin.AA_TIMER_TOP + skin.TEXT_HEIGHT, skin.AA_COLUMN_WIDTH, skin.TEXT_HEIGHT)
    assert timer.findtext('AlignRight') == 'true' and rgb(timer, 'TextColor') == skin.VALUE_RGB
    # Train, Hotkey and Done down the column's foot a padding apart, Done's bottom level with the description's and the
    # window's edge a padding under it: the confirmation dialog's kind, with no tooltips (the stock ones have none).
    boxes = []
    for screen_id, button_name in (('TrainButton', 'Train'), ('HotButton', 'Hotkey'), ('DoneButton', 'Done')):
        check_confirmation_button(found[screen_id], button_name)
        boxes.append(box(found[screen_id]))
    assert all((bx, bw) == (x, skin.AA_COLUMN_WIDTH) for bx, _, bw, _ in boxes)
    assert all(below[1] - (above[1] + above[3]) == skin.BUTTON_ROW_GAP for above, below in zip(boxes, boxes[1:]))
    description = box(found['Description'])
    assert boxes[-1][1] + boxes[-1][3] == description[1] + description[3] == skin.AA_BOTTOM
    assert box(window)[3] - (b + skin.AA_BOTTOM) == skin.PADDING
    assert boxes[0][1] - (skin.AA_TIMER_TOP + skin.TEXT_HEIGHT + digits) >= skin.PADDING


# The friends window

# Every ScreenID of the stock window by its page, all of which eqgame.exe's strings name, and the tab box's. The stock
# pages have no ScreenID; ours are ours.
STOCK_FRIENDS = {'FriendsPage': ['FriendsList', 'NameInput', 'AddButton', 'DeleteButton', 'ContactButton', 'WhoButton'],
                 'IgnorePage': ['IgnoreList', 'IgnoreNameInput', 'IgnoreAddButton', 'IgnoreDeleteButton']}


def friends_parts():
    """The friends window file, its window, its tab box, and its pages as {page's ScreenID: {ScreenID (or item, where
    it has none): part}}, the parts in the page's order."""
    root, window = screen(skin.FRIENDS_FILE)
    defined = {e.get('item'): e for e in root}
    tabs = direct_pieces(root, window)[0]
    pages = {}
    for p in tabs.findall('Pages'):
        page = defined[p.text]
        pages[page.findtext('ScreenID')] = {defined[piece.text].findtext('ScreenID') or piece.text: defined[piece.text]
                                            for piece in page.findall('Pieces')}
    return root, window, tabs, pages


def test_friends_window_keeps_every_control_the_stock_one_has():
    # A fixed size with no title bar or close box (the user's pick), so it drags by its background. Every stock control
    # is there under its ScreenID, of the stock kind, on its stock page.
    root, window, tabs, pages = friends_parts()
    assert window.get('item') == 'FriendsWindow' and window.findtext('Text') == 'Friends Window'
    assert window.findtext('Style_Titlebar') == window.findtext('Style_Sizable') == 'false'
    assert window.findtext('Style_Closebox') == 'false' and window.findtext('DrawTemplate') == skin.FRAME_TEMPLATE
    assert box(window)[2:] == (skin.FRIENDS_WIDTH, skin.FRIENDS_HEIGHT) == (174, 269)
    assert tabs.tag == 'TabBox' and tabs.findtext('ScreenID') == 'Subwindows'
    assert list(pages) == list(STOCK_FRIENDS)
    kinds = {'List': 'Listbox', 'Input': 'Editbox', 'Button': 'Button'}
    for page, controls in STOCK_FRIENDS.items():
        shown = {screen_id: part.tag for screen_id, part in pages[page].items() if not screen_id.startswith('TUI_')}
        assert shown == {c: next(kind for end, kind in kinds.items() if c.endswith(end)) for c in controls}, page
    ids = [e.findtext('ScreenID') for e in root if e.findtext('ScreenID')]
    stock = [c for controls in STOCK_FRIENDS.values() for c in controls] + ['Subwindows']
    assert sorted(ids) == sorted(stock + list(STOCK_FRIENDS)) and len(set(ids)) == len(ids)
    for folder in EQ_DIRS:
        path = Path(folder) / 'uifiles' / 'default' / skin.FRIENDS_FILE
        if folder and path.is_file():
            assert sorted(re.findall(r'<ScreenID>\s*(\w+)\s*</ScreenID>', path.read_text(encoding='latin-1'))) == sorted(
                stock)
            break


def test_friends_tabs_are_the_pages_names_like_the_aa_windows():
    # Each tab is the Actions tabs' toggle with no icon and the page's name painted on, as the AA window's (the user's
    # pick: words; see TAB_INK), centered, the open one lit. No tooltips: the names are on the tabs.
    root, _, tabs, _ = friends_parts()
    pages = [items(root, 'Page')[p.text] for p in tabs.findall('Pages')]
    assert tabs.findtext('TabBorderTemplate') == skin.TAB_BORDER
    assert tabs.findtext('PageBorderTemplate') == skin.LIST_PAGE_BORDER
    atlas = decode(files()[skin.PIECES_TEXTURE])
    anims = items(everything(), 'Ui2DAnimation')
    for page, (_, name, *_), width in zip(pages, skin.FRIENDS_PAGES, skin.FRIENDS_TAB_WIDTHS):
        assert page.find('TabText') is None and page.find('TooltipReference') is None
        assert (page.findtext('TabIcon'), page.findtext('TabIconActive')) == (f'TUI_Tab{name}Normal',
                                                                              f'TUI_Tab{name}Pressed')
        assert page.findtext('Style_Transparent') == 'true' and page.findtext('Style_Border') == 'false'
        (left, _), ink = skin.TAB_INK[name]
        assert abs(left + len(ink[0]) / 2 - width / 2) <= 0.5
        lit = {}
        for state, shift in (('Normal', 0), ('Pressed', skin.TAB_SHIFT)):
            full = cut(atlas, anims[f'TUI_Tab{name}{state}'])
            assert full.size == (width, skin.TAB_ART_HEIGHT)
            spot = (0, shift, width, shift + skin.TOGGLE_SIZE)
            tab = full.crop(spot)
            assert tab.tobytes() == as_image(skin.tab_art((), state, width, name)).crop(spot).tobytes(), (name, state)
            full.paste((0, 0, 0, 0), spot)
            assert {p[3] for p in pixels(full)} == {0}
            lit[state] = sum(sum(p[:3]) * p[3] for p in pixels(tab))
        assert lit['Pressed'] > lit['Normal'], name
    assert [name for _, name, *_ in skin.FRIENDS_PAGES] == ['Friends', 'Ignored']


def test_list_page_border_is_the_page_borders_with_a_shorter_top_row():
    # Pages that open with a list with no heading start higher, by the room over a line's ink that a padding already
    # counts, so the first name's ink sits a padding under the divider.
    assert skin.PAGE_TOP - skin.LIST_PAGE_TOP == skin.PADDING - skin.DIVIDER_TO_NAME == 3
    for side, (width, height) in skin.PAGE_BORDER_PIECES.items():
        shorter = side in ('TopLeft', 'Top', 'TopRight')
        assert skin.LIST_PAGE_BORDER_PIECES[side] == (width, height - 3 if shorter else height), side


def test_friends_window_follows_the_spacing_standard():
    root, window, tabs, pages = friends_parts()
    b = skin.BORDER
    width, height = box(window)[2:]
    # As wide as the Actions window, its tab box laid out the same way, running TAB_OVERHANG past the inside on the
    # right, where only the last tab's padding and the page border's side are.
    assert width == skin.ACTIONS_WIDTH == 174
    assert box(tabs) == (0, 0, width - 2 * b + skin.TAB_OVERHANG, height - 2 * b)
    spots, cut_at, (left, top, right, bottom) = tab_box_layout(tabs, [items(root, 'Page')[p.text]
                                                                      for p in tabs.findall('Pages')])
    toggles = [(x, y + skin.TAB_SHIFT) for x, y in spots]
    edges = [(b + x, b + x + w) for (x, _), w in zip(toggles, skin.FRIENDS_TAB_WIDTHS)]
    # The two tabs fill the row, a padding apart and from the window's sides, a pixel lower than the padding (see
    # TAB_TOP), never cut off.
    assert edges[0][0] == skin.PADDING and width - edges[-1][1] == skin.PADDING
    assert edges[1][0] - edges[0][1] == skin.PADDING and skin.FRIENDS_TAB_WIDTHS == [78, 78]
    assert [b + x for x in skin.FRIENDS_TAB_LEFTS] == [edge[0] for edge in edges]
    assert {b + y for _, y in toggles} == {skin.PADDING + 1}
    assert toggles[0][1] + skin.TOGGLE_SIZE <= cut_at
    # The Actions window's divider a padding under the tabs, across the content row. The lists have no heading, so the
    # pages start where the first name's ink, TEXT_INK_TOP into its line, is a padding under it (rounded up to a whole
    # pixel, as the tracking list's), a padding in from the window's sides and bottom.
    divider = direct_pieces(root, window)[-1]
    dx, dy, dw, dh = box(divider)
    assert divider.findtext('Animation') == 'TUI_ActionsDivider' and (b + dx, dw, dh) == (skin.PADDING, right - left, 1)
    assert dy - (toggles[0][1] + skin.TOGGLE_SIZE) == skin.PADDING
    gap = top - (dy + dh)
    assert gap == skin.DIVIDER_TO_NAME and gap - 1 < skin.PADDING - skin.TEXT_INK_TOP <= gap
    assert b + left == skin.PADDING == width - (b + right) == height - (b + bottom)
    assert (right - left, bottom - top) == (skin.FRIENDS_CONTENT_WIDTH, skin.FRIENDS_PAGE_HEIGHT)
    content = right - left
    spots_by_page = []
    for (_, _, list_id, field_id, add_id, delete_id, more), parts in zip(skin.FRIENDS_PAGES, pages.values()):
        names, strip, add = box(parts[list_id]), box(parts[f'TUI_FW_{field_id}Field']), box(parts[add_id])
        row = [box(parts[delete_id])] + [box(parts[button_id]) for button_id, _ in more]
        # The list fills the page's top, 12 names tall (a name's line each).
        assert names == (0, 0, content, skin.FRIENDS_ROWS * skin.TEXT_HEIGHT) and skin.FRIENDS_ROWS == 12
        # The field and Add a padding under it, Add a padding after the field and ending at the row's right, both as
        # tall as a dialog's button.
        assert strip[1] == add[1] == names[3] + skin.BUTTON_ROW_GAP and strip[0] == 0
        assert add[0] - (strip[0] + strip[2]) == skin.BUTTON_GAP and add[0] + add[2] == content
        assert strip[3] == skin.INPUT_HEIGHT == add[3] == skin.TEXT_BUTTON_HEIGHT
        # The buttons a padding under them, in thirds of the row a padding apart, Add over the last; the page's bottom
        # (a padding over the window's edge) under them.
        assert {r[1] for r in row} == {strip[1] + strip[3] + skin.BUTTON_ROW_GAP}
        assert [r[0] for r in row] == list(skin.FRIENDS_LEFTS[:len(row)]) and {r[2] for r in row} == {add[2]} == {50}
        assert add[0] == skin.FRIENDS_LEFTS[-1] and row[0][1] + row[0][3] == bottom - top
        assert all(b2[0] - (a[0] + a[2]) == skin.BUTTON_GAP for a, b2 in zip(row, row[1:]))
        spots_by_page.append((strip, add, row[0]))
    # The field, Add and Delete are in the same spots on both tabs; the friends' Who ends at the row's right.
    assert spots_by_page[0] == spots_by_page[1]
    who = box(pages['FriendsPage']['WhoButton'])
    assert who[0] + who[2] == content


def test_friends_lists_are_one_column_of_names_with_no_heading():
    # The stock lists' one column, 150px, and our scrollbar fill the content row. Like the stock lists they have no
    # heading, so no heading strip either.
    _, _, _, pages = friends_parts()
    for (_, _, list_id, *_), parts in zip(skin.FRIENDS_PAGES, pages.values()):
        listbox = parts[list_id]
        [column] = listbox.findall('Columns')
        assert column.find('Header') is None and not column.findtext('Heading')
        assert number(column, 'Width') == 150 == skin.FRIENDS_CONTENT_WIDTH - skin.SCROLL_WIDTH
        assert listbox.findtext('DrawTemplate') == skin.EDIT_TEMPLATE
        assert listbox.findtext('Style_VScroll') == 'true' and listbox.findtext('Style_Border') == 'false'
        assert listbox.findtext('Font') == str(skin.TEXT_FONT) and rgb(listbox, 'TextColor') == skin.TEXT_RGB
        assert listbox.find('TooltipReference') is None


def test_friends_fields_look_like_the_quantity_windows_and_the_buttons_are_the_confirmation_dialogs_kind():
    # Each name field looks like the quantity window's number field: the strip, then the see-through box on it, inset as
    # far, in the text's color. A page can't hold the quantity window's strip, a Screen (see
    # test_no_page_lists_a_screen), so the strip is a picture of the field template's look: its edge on every side and
    # corner around its background. The buttons have the stock words and no tooltips (the stock ones have none).
    root = everything()
    template = items(root, 'WindowDrawTemplate')[skin.FIELD_TEMPLATE]
    assert {e.text for e in template.find('Border') if not e.tag.startswith('Overlap')} == {'TUI_FieldEdge'}
    assert template.findtext('Background') == skin.FIELD_TEXTURE
    anims = items(root, 'Ui2DAnimation')
    edge, = colors(anims['TUI_FieldEdge'])
    fill, = set(pixels(decode(files()[skin.FIELD_TEXTURE])))
    _, _, _, pages = friends_parts()
    for (_, _, _, field_id, add_id, delete_id, more), parts in zip(skin.FRIENDS_PAGES, pages.values()):
        strip, field = parts[f'TUI_FW_{field_id}Field'], parts[field_id]
        assert strip.tag == 'StaticAnimation' and strip.findtext('Animation') == 'TUI_FriendsField'
        assert list(parts).index(strip.get('item')) < list(parts).index(field_id)
        art = cut(decode(files()[skin.PIECES_TEXTURE]), anims['TUI_FriendsField'])
        assert art.size == box(strip)[2:]
        for y in range(art.height):
            for x in range(art.width):
                ring = x in (0, art.width - 1) or y in (0, art.height - 1)
                assert art.getpixel((x, y)) == (edge if ring else fill), (x, y)
        fx, fy, fw, fh = box(strip)
        assert box(field) == (fx + skin.FIELD_PADDING, fy, fw - 2 * skin.FIELD_PADDING, fh)
        assert field.findtext('DrawTemplate') == skin.EDIT_TEMPLATE
        assert field.findtext('Style_Transparent') == 'true' and field.findtext('Style_Border') == 'false'
        assert field.findtext('Font') == str(skin.TEXT_FONT) and rgb(field, 'TextColor') == skin.TEXT_RGB
        check_confirmation_button(parts[add_id], 'Add')
        check_confirmation_button(parts[delete_id], 'Delete')
        for button_id, name in more:
            check_confirmation_button(parts[button_id], name)
    assert skin.FRIENDS_PAGES[0][-1] == (('ContactButton', 'Contact'), ('WhoButton', 'Who'))
    assert skin.FRIENDS_PAGES[1][-1] == ()


# Building

OTHER_SKIN = 'otherskin'  # a skin a player might build on instead, with --base
KEPT_FILE = 'EQUI_CharacterSelect.xml'  # a window TriageUI leaves as it is (see PLAN.md)


@pytest.fixture
def eq(tmp_path):
    """An EverQuest folder with the game's own UI files and another skin, each with the same kinds of files."""
    for name in (skin.DEFAULT_BASE, OTHER_SKIN):
        base = tmp_path / 'uifiles' / name
        (base / 'Options').mkdir(parents=True)
        (base / KEPT_FILE).write_text(f'{name} character select')
        (base / 'eqUI_targetwindow.xml').write_text(f'{name} target window')
        (base / 'EQUI_Animations.xml').write_bytes(BASE_ANIMATIONS.encode())
        (base / 'window_pieces01.tga').write_bytes(f'{name} tga'.encode())
        (base / 'Options' / 'EQUI_BuffWindow.xml').write_text('option')
    return tmp_path


@pytest.mark.parametrize('base_name', [skin.DEFAULT_BASE, OTHER_SKIN])
def test_definitions_only_the_replaced_windows_had_move_to_the_animations(eq, base_name):
    # duxaUI's player window defines the animation Blackbox, which its hot button window used: after our
    # player window replaced theirs, the client reported it missing. Such definitions move into our
    # animations file, whichever skin the build is on; ones nothing else uses don't, nor the replaced window
    # itself. Our hot button window has since replaced theirs too, so a window we keep stands in for it here.
    base = eq / 'uifiles' / base_name
    blackbox =('<Ui2DAnimation item="Blackbox">\r\n    <Cycle>true</Cycle>\r\n'
                '    <Frames><Texture>window_pieces22.tga</Texture></Frames>\r\n  </Ui2DAnimation>')
    (base / 'EQUI_PlayerWindow.xml').write_bytes((
        '<XML>\r\n  ' + blackbox + '\r\n'
        '  <Ui2DAnimation item="OnlyHere"><Cycle>true</Cycle></Ui2DAnimation>\r\n'
        '  <StaticAnimation item="PW_Box"><Animation>Blackbox</Animation></StaticAnimation>\r\n'
        '  <Screen item="PlayerWindow"><Pieces>PW_Box</Pieces></Screen>\r\n</XML>\r\n').encode())
    (base / KEPT_FILE).write_text('<XML><StaticAnimation item="CS"><Animation>Blackbox</Animation>'
                                  '</StaticAnimation></XML>')
    out = skin.build(eq, base_name)
    animations = (out / skin.ANIMATIONS_FILE).read_bytes().decode('latin-1')
    assert animations.count('item="Blackbox"') == 1 and 'OnlyHere' not in animations and 'PW_Box' not in animations
    assert '\n' not in animations.replace('\r\n', '')
    root = ET.fromstring(animations.split('\n', 1)[1])
    assert items(root, 'Ui2DAnimation')['Blackbox'].findtext('Frames/Texture') == 'window_pieces22.tga'
    # Before our own definitions, inside the file.
    assert animations.index('item="Blackbox"') < animations.index(f'item="{skin.FRAME_TEMPLATE}"')


def test_the_spell_icons_replace_the_base_skins(eq):
    # The client draws every spell's icon from A_SpellGems and A_SpellIcons, by name: ours, defined once over our own
    # sheets, the base's definitions taken out (in default's spacing too) and its sheets never copied.
    base = eq / 'uifiles' / skin.DEFAULT_BASE
    stock = ('<Ui2DAnimation item = "A_SpellGems"><Frames><Texture>gemicons01.tga</Texture></Frames></Ui2DAnimation>'
             '<Ui2DAnimation item = "A_SpellIcons"><Frames><Texture>Spells01.tga</Texture></Frames></Ui2DAnimation>')
    (base / 'EQUI_Animations.xml').write_bytes(BASE_ANIMATIONS.replace('</XML>', f'  {stock}\r\n</XML>').encode())
    (base / 'gemicons01.tga').write_bytes(b'the stock gem icons')
    out = skin.build(eq)
    animations = (out / skin.ANIMATIONS_FILE).read_bytes().decode('latin-1')
    assert 'gemicons01.tga' not in animations and 'Spells01.tga' not in animations
    defined = items(ET.fromstring(animations.split('?>', 1)[1]), 'Ui2DAnimation')
    for name, sheets in (('A_SpellGems', skin.GEM_ICON_SHEETS), ('A_SpellIcons', skin.SPELL_ICON_SHEETS)):
        assert animations.count(f'item="{name}"') == 1
        assert [frame.findtext('Texture') for frame in defined[name].findall('Frames')] == list(sheets)
        assert all((out / sheet).is_file() for sheet in sheets)
    assert not (out / 'gemicons01.tga').exists()


def snapshot(folder):
    return {path.relative_to(folder): path.read_bytes() for path in folder.rglob('*') if path.is_file()}


def test_a_build_on_default_is_only_ours(eq):
    # The client falls back to default file by file, so nothing is copied: every file in the skin is ours, and
    # none is a copy of the game's or another skin's.
    base = eq / 'uifiles' / skin.DEFAULT_BASE
    before = snapshot(base)
    out = skin.build(eq)
    assert out == eq / 'uifiles' / 'TriageUI'
    assert {path.name for path in out.iterdir()} == {skin.MARKER_FILE, *files()}
    for name, data in files().items():
        assert (out / name).read_bytes() == data
    theirs = {*snapshot(base).values(), *snapshot(eq / 'uifiles' / OTHER_SKIN).values()}
    assert not set(snapshot(out).values()) & theirs
    assert snapshot(base) == before


def test_a_build_on_another_skin_copies_it_and_adds_ours(eq):
    base = eq / 'uifiles' / OTHER_SKIN
    before = snapshot(base)
    out = skin.build(eq, OTHER_SKIN)
    names = {path.name for path in out.iterdir()}
    assert names == {KEPT_FILE, 'window_pieces01.tga', skin.MARKER_FILE, *files()}
    assert (out / KEPT_FILE).read_text() == f'{OTHER_SKIN} character select'
    for name, data in files().items():
        assert (out / name).read_bytes() == data
    assert snapshot(base) == before


def test_a_base_without_animations_extends_the_default_ones(eq):
    (eq / 'uifiles' / OTHER_SKIN / 'EQUI_Animations.xml').unlink()
    default = eq / 'uifiles' / skin.DEFAULT_BASE
    (default / 'EQUI_Animations.xml').unlink()
    (default / 'equi_animations.xml').write_text('<XML>\n  <Ui2DAnimation item="A_Default" />\n</XML>\n')
    out = skin.build(eq, OTHER_SKIN)
    assert 'A_Default' in (out / skin.ANIMATIONS_FILE).read_text()


def test_build_needs_some_animations_file(eq):
    (eq / 'uifiles' / skin.DEFAULT_BASE / 'EQUI_Animations.xml').unlink()
    with pytest.raises(skin.BuildError, match='default has no EQUI_Animations.xml'):
        skin.build(eq)
    (eq / 'uifiles' / OTHER_SKIN / 'EQUI_Animations.xml').unlink()
    with pytest.raises(skin.BuildError, match=f'Neither {OTHER_SKIN} nor default'):
        skin.build(eq, OTHER_SKIN)


def test_rebuild_replaces_only_its_own_output(eq):
    out = skin.build(eq)
    (out / 'stale.xml').write_text('old')
    skin.build(eq)
    assert not (out / 'stale.xml').exists()


def test_build_leaves_a_folder_it_did_not_build_alone(eq):
    out = eq / 'uifiles' / 'TriageUI'
    out.mkdir()
    (out / 'mine.xml').write_text('keep')
    with pytest.raises(skin.BuildError, match='left alone'):
        skin.build(eq)
    assert snapshot(out) == {Path('mine.xml'): b'keep'}


@pytest.mark.parametrize('base_name', [skin.DEFAULT_BASE, OTHER_SKIN])
def test_build_never_writes_into_the_base_skin(eq, base_name):
    base = eq / 'uifiles' / base_name
    before = snapshot(base)
    with pytest.raises(skin.BuildError, match='must not be the base'):
        skin.build(eq, base_name, out=base)
    assert snapshot(base) == before


def test_build_needs_the_base_skin(tmp_path):
    with pytest.raises(skin.BuildError, match='no skin folder'):
        skin.build(tmp_path)


def test_main_reports_success_and_errors(eq, capsys):
    assert skin.main(['--eq', str(eq)]) == 0
    printed = capsys.readouterr().out
    assert f'Built TriageUI {skin.VERSION} into ' in printed and '/load TriageUI 1 ' in printed
    assert skin.main(['--eq', str(eq), '--base', 'missing']) == 1
    assert 'no skin folder' in capsys.readouterr().err


def test_the_built_folder_names_its_version_and_license(eq):
    marker = (skin.build(eq) / skin.MARKER_FILE).read_text()
    assert f'TriageUI {skin.VERSION}\'s build_skin.py' in marker and skin.LICENSE_NOTICE in marker


# The license

def test_the_license_file_holds_the_notice_and_the_legal_code():
    text = (REPO / 'LICENSE').read_text(encoding='utf-8')
    assert text.startswith('TriageUI\nCopyright 2026 Sebik <Europa>\n')
    # The built files' notice points to the license this file holds.
    url = skin.LICENSE_NOTICE.rsplit(' ', 1)[1]
    assert url == 'https://creativecommons.org/licenses/by-nc-sa/4.0/' and url in text
    assert '\nAttribution-NonCommercial-ShareAlike 4.0 International\n' in text
    assert 'Section 1 -- Definitions.' in text and 'Section 8 -- Interpretation.' in text


def test_the_readme_gives_the_license():
    readme = (REPO / 'README.md').read_text(encoding='utf-8')
    section = readme.split('\n## License\n', 1)[1].split('\n## ', 1)[0]
    assert '(CC BY-NC-SA 4.0)' in section and '](LICENSE)' in section
    assert 'Sebik &lt;Europa&gt;' in section


def test_the_readme_warns_against_a_chat_name_starting_with_a_space():
    # Zeal takes such a window for a tell window and marks it not to load at the next login, even with tell windows off.
    readme = (REPO / 'README.md').read_text(encoding='utf-8')
    chat = readme.split('\n## The chat windows\n', 1)[1].split('\n## ', 1)[0]
    assert "Don't blank a chat window's name with a space." in chat
    troubleshooting = readme.split('\n## Troubleshooting\n', 1)[1].split('\n## ', 1)[0]
    assert '`ChatWindow<n>_Language=@42`' in troubleshooting and '`ChatWindow<n>_Language=0`' in troubleshooting


# The window plan

PLAN_FILE = Path(__file__).resolve().parent.parent / 'PLAN.md'


def plan_sections():
    """PLAN.md's window files, as {section heading: [file on each table row]}."""
    sections = {}
    heading = None
    for line in PLAN_FILE.read_text(encoding='utf-8').splitlines():
        if line.startswith('## '):
            heading = line[3:].strip()
            sections[heading] = []
        elif heading and line.startswith('|'):
            sections[heading] += re.findall(r'`(EQUI_\w+\.xml)`', line)
    return sections


def test_the_plan_marks_the_built_windows_done():
    assert set(plan_sections()['Done']) == set(skin.WINDOW_FILES)


def test_the_plan_lists_each_window_once():
    listed = [name.lower() for names in plan_sections().values() for name in names]
    assert listed and len(listed) == len(set(listed))


def test_the_plan_lists_every_window_the_client_loads():
    for folder in EQ_DIRS:
        path = Path(folder) / 'uifiles' / 'default' / 'EQUI.xml'
        if folder and path.is_file():
            break
    else:
        pytest.skip('no EverQuest folder with uifiles/default here')
    loaded = set(re.findall(r'<Include>\s*([^<\s]+)\s*</Include>', path.read_text(encoding='latin-1')))
    windows = {name.lower() for name in loaded} - {'sidl.xml', 'equi_animations.xml', 'equi_templates.xml'}
    listed = {name.lower() for names in plan_sections().values() for name in names}
    assert windows and windows <= listed


# The preview renderer (tools/preview.py)

@functools.cache
def preview_module():
    path = Path(__file__).resolve().parent.parent / 'tools' / 'preview.py'
    spec = importlib.util.spec_from_file_location('preview', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preview_draws_every_window_at_its_size_on_its_panel(tmp_path):
    preview = preview_module()
    drawer = preview.Preview(files(), eq_dir=tmp_path)  # no EverQuest folder here: grey squares for icons
    for name in skin.WINDOW_FILES:
        root, window = screen(name)
        images = drawer.render(name)
        # One image per page of a tab box (the Actions window's four), else one.
        assert len(images) == max([len(tab.findall('Pages')) for tab in root.iter('TabBox')] + [1]), name
        for image in images:
            if window.get('item') == 'ContainerWindow':
                assert image.size == bag_layout(*preview.BAG)[0]  # the game sizes the bag window
            else:
                assert image.size == box(window)[2:], name
            width, height = image.size
            assert image.getpixel((width // 2, height - 3))[3] == 255, name  # the opaque panel
            assert image.getpixel((0, 0))[3] < 20, name  # a rounded corner


def test_preview_saves_each_window_scaled_on_a_backdrop(tmp_path):
    preview = preview_module()
    [path] = preview.save(preview.Preview(files(), eq_dir=tmp_path), [skin.QUANTITY_FILE], tmp_path, scale=2)
    _, window = screen(skin.QUANTITY_FILE)
    width, height = box(window)[2:]
    image = Image.open(path)
    assert path.name == 'EQUI_QuantityWnd.png'
    assert image.size == (2 * (width + 2 * preview.MARGIN), 2 * (height + 2 * preview.MARGIN))
    assert image.convert('RGBA').getpixel((0, 0)) == preview.BACKDROP


def test_quantity_title_is_painted_as_the_preview_draws_a_line_of_text():
    # The game would center the window's title under Close, so the name is painted into the bar's art in font 3's look
    # (see QUANTITY_TITLE_INK): the ink's coverage as this tool draws a line of font 3, at the 16 alpha steps.
    preview = preview_module()
    if not any(Path(path).is_file() for path in preview.ARIAL):
        pytest.skip('no Arial to draw font 3 with')
    steps = preview.text_mask('Quantity', skin.TEXT_FONT).point(lambda v: round(v / skin.STEP))
    left, top, right, bottom = steps.getbbox()
    assert skin.QUANTITY_TITLE_INK == tuple(''.join(f'{steps.getpixel((x, y)):x}' for x in range(left, right))
                                            for y in range(top, bottom))


def title_ink_columns(image, bar_height, close_left):
    """The columns of a drawn window's title bar, left of its close box, where anything is drawn over the bar (as it
    is at the inside's right edge, past the close box)."""
    b = skin.BORDER
    bare = image.width - b - 1
    return [x for x in range(b, close_left)
            if any(image.getpixel((x, y)) != image.getpixel((bare, y)) for y in range(b, b + bar_height - 1))]


def test_preview_centers_a_title_across_its_bar_as_the_game_does(tmp_path):
    # DrawTitleBar centers the window's name across the bar (the quantity window's ran under its Close in game). The
    # quantity window has no title, so its bar shows only its painted name there.
    preview = preview_module()
    b = skin.BORDER
    [item] = preview.Preview(files(), eq_dir=tmp_path).render(skin.ITEM_FILE)
    close_left = skin.ITEM_WIDTH - b - skin.CLOSE_BOX_INSET - skin.CLOSE_WIDTH
    columns = title_ink_columns(item, skin.ITEM_TITLE_HEIGHT, close_left)
    assert columns and abs((columns[0] + columns[-1] + 1) / 2 - skin.ITEM_WIDTH / 2) <= 1
    [quantity] = preview.Preview(files(), eq_dir=tmp_path).render(skin.QUANTITY_FILE)
    close_left = skin.QUANTITY_WIDTH - b - skin.CLOSE_BOX_INSET - skin.CLOSE_WIDTH
    columns = title_ink_columns(quantity, skin.ITEM_TITLE_HEIGHT, close_left)
    left = b + skin.QUANTITY_TITLE_INK_AT[0]
    assert columns[0] == left and columns[-1] < left + len(skin.QUANTITY_TITLE_INK[0])


def test_close_is_painted_as_the_preview_draws_a_buttons_own_text():
    # The game writes nothing on a close box, so Close's name is painted into its art in font 2's look (see CLOSE_INK):
    # the ink's coverage as this tool draws Accept's kind of text (font 2) on a button Close's size, at the 16 alpha
    # steps, from its top left.
    preview = preview_module()
    if not any(Path(path).is_file() for path in preview.ARIAL):
        pytest.skip('no Arial to draw font 2 with')
    mask = preview.button_text_mask('Close', (skin.CLOSE_WIDTH, skin.TEXT_BUTTON_HEIGHT), skin.ACTION_FONT)
    left, top, right, bottom = mask.getbbox()
    assert (left, top) == skin.CLOSE_INK_AT
    assert skin.CLOSE_INK == tuple(''.join(f'{round(mask.getpixel((x, y)) / skin.STEP):x}' for x in range(left, right))
                                   for y in range(top, bottom))


def test_tab_names_are_painted_as_the_preview_draws_a_buttons_own_text():
    # Like Close's: each AA and friends tab's name is the ink's coverage as this tool draws a button's own text in font 2
    # centered on a button the tab's size, at the 16 alpha steps. The widest AA name, "PoP Advance", has a padding either
    # side.
    preview = preview_module()
    if not any(Path(path).is_file() for path in preview.ARIAL):
        pytest.skip('no Arial to draw font 2 with')
    tabs = [(name, width) for (_, _, name, _), width in zip(skin.AA_PAGES, skin.AA_TAB_WIDTHS)]
    tabs += [(name, width) for (_, name, *_), width in zip(skin.FRIENDS_PAGES, skin.FRIENDS_TAB_WIDTHS)]
    assert sorted(name for name, _ in tabs) == sorted(skin.TAB_INK)
    for name, width in tabs:
        mask = preview.button_text_mask(name, (width, skin.TOGGLE_SIZE), skin.ACTION_FONT)
        left, top, right, bottom = mask.getbbox()
        assert skin.TAB_INK[name] == ((left, top), tuple(
            ''.join(f'{round(mask.getpixel((x, y)) / skin.STEP):x}' for x in range(left, right))
            for y in range(top, bottom))), name
    (left, _), ink = skin.TAB_INK['PoP Advance']
    assert left == skin.AA_TAB_WIDTH - (left + len(ink[0])) == skin.PADDING


def test_preview_fills_in_what_the_game_writes_in_the_give_window(tmp_path):
    # The NPC's name (a label with no EQType, sampled by its ScreenID), each coin's name and its amount in the middle of
    # its box, and items in the first slots.
    preview = preview_module()
    [image] = preview.Preview(files(), eq_dir=tmp_path).render(skin.GIVE_FILE)
    _, _, found = give_parts()

    def region(screen_id, left=0, right=None):
        x, y, width, height = box(found[screen_id])
        right = width if right is None else right
        return image.crop((skin.BORDER + x + left, skin.BORDER + y, skin.BORDER + x + right, skin.BORDER + y + height))

    def bright(part):
        return sum(1 for p in pixels(part) if min(p[:3]) > 150)

    assert preview.LABEL_TEXT['GVW_NPCName'] == 'Captain Tillin' and bright(region('GVW_NPCName'))
    name_end = skin.PADDING + skin.COIN_CAPTION_WIDTH
    for screen_id, _ in skin.GIVE_COINS:
        assert bright(region(screen_id, right=name_end)) and bright(region(screen_id, name_end)), screen_id
    # A button's text is lowered to the game's ink like a label's, so the amount's digits are where the game draws them
    # (see COIN_CAPTION_TOP), within half a pixel, and the name's ink is level with them.
    def ink_rows(part):
        rows = [y for y in range(part.height) if bright(part.crop((0, y, part.width, y + 1)))]
        return rows[0], rows[-1] + 1

    amount = ink_rows(region('GVW_MyMoney0', name_end))
    ink_top = skin.COIN_TEXT_TOP + skin.TEXT_INK_TOP
    assert ink_top - 0.5 <= amount[0] and amount[1] <= ink_top + 9 + 0.5
    for screen_id, _ in skin.GIVE_COINS:
        assert ink_rows(region(screen_id, skin.PADDING, name_end)) == amount, screen_id
    assert preview.GIVE_ITEMS == 2
    slots = [pixels(region(f'GVW_MyItemSlot{n}')) for n in range(4)]
    assert slots[0] != slots[3] and slots[1] != slots[3] and slots[2] == slots[3]


def test_preview_fills_in_what_the_game_writes_in_the_trade_window(tmp_path):
    # Both names, each coin's amount beside its name, the first slots on each side holding items, and the divider drawn
    # from its template's background.
    preview = preview_module()
    [image] = preview.Preview(files(), eq_dir=tmp_path).render(skin.TRADE_FILE)
    _, _, found = trade_parts()

    def region(key, left=0):
        x, y, width, height = box(found[key])
        return image.crop((skin.BORDER + x + left, skin.BORDER + y, skin.BORDER + x + width, skin.BORDER + y + height))

    def bright(part):
        return sum(1 for p in pixels(part) if min(p[:3]) > 150)

    assert preview.LABEL_TEXT['TRDW_MyName'] == 'Sebik'
    assert bright(region('TRDW_HisName')) and bright(region('TRDW_MyName'))
    for prefix, _, first in skin.TRADE_SIDES:
        for n in range(len(skin.COIN_CAPTIONS)):
            coin = f'TRDW_{prefix}Money{n}'
            assert bright(region(coin, skin.PADDING + skin.COIN_CAPTION_WIDTH)) and bright(region(f'TUI_{coin}_Caption'))
        slots = [pixels(region(f'TRDW_TradeSlot{first + n}')) for n in range(8)]
        assert slots[0] != slots[7] and slots[2:] == [slots[7]] * 6
    panel = image.getpixel((skin.BORDER + skin.TRADE_DIVIDER_X + 1, skin.BORDER + skin.TRADE_COINS_TOP - 3))
    line = set(pixels(region('TUI_TRDW_Divider')))
    assert len(line) == 1 and line != {panel}


def test_preview_fills_in_what_the_game_writes_in_the_loot_window(tmp_path):
    # The corpse's name, and items in the first slots.
    preview = preview_module()
    [image] = preview.Preview(files(), eq_dir=tmp_path).render(skin.LOOT_FILE)
    root, _, found = loot_parts()
    panel = found['LootInvWnd']
    left, top = box(panel)[:2]

    def region(x, y, width, height):
        return image.crop((skin.BORDER + x, skin.BORDER + y, skin.BORDER + x + width, skin.BORDER + y + height))

    assert preview.LABEL_TEXT['LW_CorpseName'] == "a gnoll pup's corpse"
    assert sum(1 for p in pixels(region(*box(found['LW_CorpseName']))) if min(p[:3]) > 150)
    assert preview.LOOT_ITEMS == 3
    slots = [pixels(region(left + x, top + y, width, height))
             for x, y, width, height in (box(slot) for slot in direct_pieces(root, panel))]
    assert all(slot != slots[-1] for slot in slots[:3]) and slots[3:] == [slots[-1]] * 27


def test_preview_fills_in_what_the_game_writes_in_the_bank_window(tmp_path):
    # The banker's name, the shared caption within its column, seven digits of platinum clear of their coin's name,
    # items in the first slots of each grid, and the divider drawn from its template's background.
    preview = preview_module()
    [image] = preview.Preview(files(), eq_dir=tmp_path).render(skin.BANK_FILE)
    _, _, found = bank_parts()

    def region(key, left=0, right=None):
        x, y, width, height = box(found[key])
        right = width if right is None else right
        return image.crop((skin.BORDER + x + left, skin.BORDER + y, skin.BORDER + x + right, skin.BORDER + y + height))

    def bright(part):
        return sum(1 for p in pixels(part) if min(p[:3]) > 150)

    def columns(part):
        return [x for x in range(part.width) if bright(part.crop((x, 0, x + 1, part.height)))]

    assert preview.LABEL_TEXT['BW_BankerName'] == 'Banker Denston' and bright(region('BW_BankerName'))
    # The caption's ink ends short of its label's right edge, so none of it is cut off.
    ink = columns(region('BW_SharedBankLabel'))
    assert ink and ink[-1] + 1 < skin.SHARED_WIDTH
    # The amount's ink starts more than a padding after the name's label ends.
    name_end = skin.PADDING + skin.COIN_CAPTION_WIDTH
    assert preview.BUTTON_TEXT['BW_Money0'] == '1234567'
    assert not bright(region('BW_Money0', name_end, name_end + skin.PADDING))
    for screen_id, _, _ in skin.BANK_COINS:
        assert bright(region(screen_id, right=name_end)) and bright(region(screen_id, name_end)), screen_id
    assert (preview.BANK_ITEMS, preview.SHARED_ITEMS) == (7, 2)
    for prefix, count, held in (('SharedBank', 10, 2), ('Bank', 30, 7)):
        slots = [pixels(region(f'BW_{prefix}Slot{n}')) for n in range(count)]
        assert all(slot != slots[-1] for slot in slots[:held]) and slots[held:] == [slots[-1]] * (count - held)
    panel = image.getpixel((skin.BORDER + skin.BANK_DIVIDER_X + 1, skin.BORDER + skin.BANK_SLOTS_TOP - 3))
    line = set(pixels(region('TUI_BW_Divider')))
    assert len(line) == 1 and line != {panel}


def test_preview_fills_in_the_skills_list(tmp_path):
    # More skills than rows, so every row in view has a name and a value.
    preview = preview_module()
    [image] = preview.Preview(files(), eq_dir=tmp_path).render(skin.SKILLS_FILE)
    _, _, found = skills_parts()
    x, y = box(found['SkillList'])[:2]
    (_, name_width), _, (_, value_width) = skin.SKILLS_COLUMNS
    rows = preview.LIST_ROWS['SkillList']
    assert len(rows) > skin.SKILLS_ROWS and 'Percussion Instruments' in {row[0] for row in rows}

    def ink(left, width, row):
        top = skin.BORDER + y + skin.RAID_HEADER_HEIGHT + row * skin.TEXT_HEIGHT
        part = image.crop((skin.BORDER + x + left, top, skin.BORDER + x + left + width, top + skin.TEXT_HEIGHT))
        return [column for column in range(part.width)
                if any(min(part.getpixel((column, r))[:3]) > 150 for r in range(part.height))]

    for row in range(skin.SKILLS_ROWS):
        assert ink(0, name_width, row) and ink(name_width, value_width, row), row
    # The widest name, as drawn here, ends a padding or more before the value column.
    assert preview.text_mask('Percussion Instruments', skin.TEXT_FONT).getbbox()[2] <= name_width - skin.PADDING


def test_preview_fills_in_the_spell_book(tmp_path):
    # Each sample spell's icon in its frame and its name in ink under it, the spots past them empty, both page numbers,
    # the memorizing bar part filled along the top, the longest name any class can scribe wrapped onto its three lines,
    # each centered, and no red showing round the detrimental samples' icons, the client's art stretched to the slot.
    preview = preview_module()
    [image] = preview.Preview(files(), eq_dir=tmp_path).render(skin.SPELLBOOK_FILE)
    _, _, found = spellbook_parts()

    def region(key, left=0, top=0, width=None, height=None):
        x, y, w, h = box(found[key])
        x, y = skin.BORDER + x + left, skin.BORDER + y + top
        return image.crop((x, y, x + (w if width is None else width), y + (h if height is None else height)))

    def bright(part):
        return sum(1 for p in pixels(part) if min(p[:3]) > 150)

    def inked(part):
        return sum(1 for p in pixels(part) if max(p[:3]) < 110)

    spells = len(preview.BOOK)
    assert spells == 13 and 'Transons Phantasmal Protection' in {name for name, _ in preview.BOOK}
    margin = skin.BOOK_SLOT_MARGIN

    def shows(n, cell):
        """Whether book slot n shows our icon for cell: its every opaque pixel."""
        drawn, icon = region(f'SBW_Spell{n}', margin, margin, skin.BOOK_ICON, skin.BOOK_ICON), spell_icon(cell)
        return all(d == i for d, i in zip(pixels(drawn), pixels(icon)) if i[3] == 255)

    for n in range(skin.BOOK_SPELLS):
        assert shows(n, preview.BOOK[n][1]) if n < spells else not any(shows(n, c) for _, c in preview.BOOK), n
        assert bool(inked(region(f'SBW_SpellName{n}'))) == (n < spells), n
    harmful = sorted(int(key[len('SBW_Spell'):]) for key in preview.HARMFUL if key.startswith('SBW_Spell'))
    assert [preview.BOOK[n][0] for n in harmful] == ['Root', 'Stun']
    ring = [(x, y) for x in range(skin.BOOK_SLOT) for y in range(skin.BOOK_SLOT)
            if not (margin <= x < margin + skin.BOOK_ICON and margin <= y < margin + skin.BOOK_ICON)]
    for n in harmful:  # no red round the icon, where the stretched bars would show past it
        slot = region(f'SBW_Spell{n}')
        assert not [p for p in (slot.getpixel(xy) for xy in ring) if p[0] > 150 and p[1] < 100], n
    assert preview.BOOK_PAGES == ('12', '13')
    assert bright(region('SBW_LeftPageNum')) and bright(region('SBW_RightPageNum'))
    bar = region('SBW_Memorize_Gauge')
    assert preview.GAUGES[skin.MEMORIZE_TYPE] == 0.4
    assert bar.getpixel((0, 0)) != bar.getpixel((bar.width - 1, 0))
    if not any(Path(path).is_file() for path in preview.ARIAL):
        pytest.skip('no Arial to draw font 3 with')
    longest = [n for n, (name, _) in enumerate(preview.BOOK) if name == 'Transons Phantasmal Protection'][0]
    for line in range(skin.BOOK_NAME_LINES):
        ink = region(f'SBW_SpellName{longest}', 0, line * skin.TEXT_HEIGHT, None, skin.TEXT_HEIGHT)
        mask = Image.new('L', ink.size)
        mask.putdata([255 if max(p[:3]) < 110 else 0 for p in pixels(ink)])
        left, _, right, _ = mask.getbbox()
        assert abs(left - (ink.width - right)) <= 2, line  # centered, but for rounding and the letters' side bearings
    short = [n for n, (name, _) in enumerate(preview.BOOK) if name == 'Root'][0]  # one line, the others blank
    assert not inked(region(f'SBW_SpellName{short}', 0, skin.TEXT_HEIGHT, None, 2 * skin.TEXT_HEIGHT))


def test_preview_fills_in_the_inventory_window(tmp_path):
    # Who you are and both bars, part filled, in the middle, the stats and numbers beside them, six digits of platinum
    # clear of their coin's name, items in the held slots and each empty worn slot's own icon.
    preview = preview_module()
    [image] = preview.Preview(files(), eq_dir=tmp_path).render(skin.INVENTORY_FILE)  # grey squares for items here
    _, _, found = inventory_parts()
    panel = image.getpixel((skin.BORDER + skin.INV_MIDDLE_X + 2, skin.BORDER + skin.INV_MIDDLE_TOP + 150))

    def region(key, left=0, right=None):
        x, y, width, height = box(found[key])
        right = width if right is None else right
        return image.crop((skin.BORDER + x + left, skin.BORDER + y, skin.BORDER + x + right, skin.BORDER + y + height))

    def inked(part):
        return sum(1 for p in pixels(part) if p != panel)

    def bright(part):
        return sum(1 for p in pixels(part) if min(p[:3]) > 150)

    for key in ('NameLabel', 'LevelClassLabel', 'TUI_IW_Class', 'DeityLabel', 'ACNumberLabel', 'ATKNumberLabel',
                'WeightNumberLabel', 'TUI_IW_WeightMax', 'STRNumberLabel', 'CHANumberLabel'):
        assert inked(region(key)), key
    assert preview.LABELS[3] == 'Shadow Knight' and preview.LABELS[4] == 'Mithaniel Marr'
    for key, value in (('ExpGauge', 0.45), ('TUI_IW_AABar', 0.12)):
        bar = region(key)
        assert preview.GAUGES[number(found[key], 'EQType')] == value
        assert bar.getpixel((0, 0)) != bar.getpixel((bar.width - 1, 0)), key
    assert inked(region('TUI_IW_AACaption')) and inked(region('TUI_IW_WeightMax'))
    # The weight's max ends where the stats' values do (150 and CHA's 60 share their last digit's column).
    weight_max, cha = region('TUI_IW_WeightMax'), region('CHANumberLabel')

    def last_column(part):
        return max(x for x in range(part.width) if any(part.getpixel((x, y)) != panel for y in range(part.height)))

    assert last_column(weight_max) + box(found['TUI_IW_WeightMax'])[0] == last_column(cha) + box(found['CHANumberLabel'])[0]
    name_end = skin.PADDING + skin.COIN_CAPTION_WIDTH
    assert preview.BUTTON_TEXT['IW_Money0'] == '123456'
    assert not bright(region('IW_Money0', name_end, name_end + skin.PADDING))
    for n in range(4):
        assert bright(region(f'IW_Money{n}', right=name_end)) and bright(region(f'IW_Money{n}', name_end)), n
    held = {eq_type for eq_type, *_ in skin.INV_WORN} & preview.HELD_SLOTS
    assert held == {2, 13, 17}
    slots = {eq_type: pixels(region(f'InvSlot{eq_type}')) for eq_type, *_ in skin.INV_WORN}
    for eq_type in held:
        assert set(slots[eq_type]) == {preview.PLACEHOLDER_RGBA}, eq_type
    icons = {icon: tuple(slots[eq_type]) for eq_type, icon, _, _ in skin.INV_WORN if eq_type not in held}
    assert len(set(icons.values())) == len(icons) == 15


def test_preview_fills_in_the_inspect_window(tmp_path):
    # The player's name on the title bar, their message wrapped over more than one line inside the strip, items in the
    # slots they wear and each empty slot's own icon.
    preview = preview_module()
    [image] = preview.Preview(files(), eq_dir=tmp_path).render(skin.INSPECT_FILE)  # grey squares for items here
    _, _, found = inspect_parts()
    top = skin.BORDER + skin.INSPECT_TITLE_HEIGHT  # the controls' inside, in the window

    def region(key):
        x, y, width, height = box(found[key])
        return image.crop((skin.BORDER + x, top + y, skin.BORDER + x + width, top + y + height))

    def bright(part):
        return sum(1 for p in pixels(part) if min(p[:3]) > 150)

    assert preview.TITLES['InspectWnd'] == 'Sebik'
    assert bright(image.crop((skin.BORDER, skin.BORDER, skin.INSPECT_WIDTH - skin.BORDER, top - 1)))
    message = region('INSW_Edit')
    lines = {y // skin.TEXT_HEIGHT for y in range(message.height)
             if any(min(message.getpixel((x, y))[:3]) > 150 for x in range(message.width))}
    assert {0, 1} <= lines
    held = {n for n in range(1, 22)} & preview.INSPECTED_SLOTS
    assert held == {2, 13, 14, 17}
    slots = {n: pixels(region(f'InvSlot{n}')) for n in range(1, 22)}
    for n in held:
        assert set(slots[n]) == {preview.PLACEHOLDER_RGBA}, n
    icons = {icon: tuple(slots[eq_type]) for eq_type, icon, _, _ in skin.INV_WORN if eq_type not in held}
    assert len(set(icons.values())) == len(icons)


@pytest.mark.parametrize('heading, label', [(0, 'N'), (90, 'E'), (180, 'S'), (270, 'W')])
def test_preview_slides_the_compass_strip_to_the_heading(tmp_path, monkeypatch, heading, label):
    # The strips go where the stock art's line-up puts them, so the direction faced has its label centered over the
    # pointer (the labels either side are 22.5px away, outside the columns looked at), and the frame is left alone.
    preview = preview_module()
    monkeypatch.setattr(preview, 'HEADING', heading)
    drawer = preview.Preview(files(), eq_dir=tmp_path)
    [image] = drawer.render(skin.COMPASS_FILE)
    b = skin.BORDER
    pointer = b + skin.COMPASS_POINTER_X
    color = skin.snapped((*{name: rgb for name, _, rgb in skin.COMPASS_MARKS}[label], 255))
    top = b + skin.COMPASS_LETTERS_TOP
    ink = {x for x in range(pointer - 12, pointer + 13) for y in range(top, top + skin.LABEL_HEIGHT)
           if image.getpixel((x, y)) == color}
    assert (min(ink) + max(ink) + 1) / 2 == pointer + 0.5
    frame, _ = drawer.frame(skin.FRAME_TEMPLATE, *image.size)
    width, height = image.size
    border = [(x, y) for x in range(width) for y in range(height)
              if not (b <= x < width - b and b <= y < height - b)]
    assert all(image.getpixel(spot) == frame.getpixel(spot) for spot in border)


def test_preview_draws_the_tracking_window_with_its_dropdowns_and_con_colored_names(tmp_path):
    # More names than rows, each in its con's color, from the list's top (it has no heading row); each dropdown its
    # outline, the choice it shows and its arrow at the right; each filter its square.
    preview = preview_module()
    [image] = preview.Preview(files(), eq_dir=tmp_path).render(skin.TRACKING_FILE)
    _, _, found = tracking_parts()

    def region(key, left=0, top=0, width=None, height=None):
        x, y, w, h = box(found[key])
        x, y = skin.BORDER + x + left, skin.BORDER + y + top
        return image.crop((x, y, x + (w if width is None else width), y + (h if height is None else height)))

    assert len(preview.TRACKED) > skin.TRACK_ROWS and len(preview.LIST_RGB['TRW_TrackingList']) == len(preview.TRACKED)
    column = skin.TRACK_COLUMNS[0][1]
    for row, (_, con) in enumerate(preview.TRACKED[:skin.TRACK_ROWS]):
        line = pixels(region('TRW_TrackingList', 0, row * skin.TEXT_HEIGHT, column, skin.TEXT_HEIGHT))
        red, green, blue = skin.TRACK_FILTERS[con][3]
        # Its ink leans the con's way: the brightest pixel is brightest in the con color's channels.
        brightest = max(line, key=lambda p: sum(p[:3]))
        assert all((brightest[c] > 100) == (value > 0) for c, value in enumerate((red, green, blue))), row
    for _, _, combo_id, _, _ in skin.TRACK_COMBOS:
        text = region(combo_id, 1, 1, skin.TRACK_COMBO_WIDTH - 2 - skin.SCROLL_WIDTH, skin.COMBO_HEIGHT - 2)
        arrow = region(combo_id, skin.TRACK_COMBO_WIDTH - 1 - skin.SCROLL_WIDTH, 1, skin.SCROLL_WIDTH,
                       skin.COMBO_ARROW_HEIGHT)
        assert any(min(p[:3]) > 150 for p in pixels(text)), combo_id
        assert len(set(pixels(arrow))) > 1, combo_id
        edge = region(combo_id, 0, 0, None, 1)
        assert len(set(pixels(edge))) == 1 and pixels(edge)[0] != image.getpixel((skin.BORDER, skin.BORDER + 200))
    assert preview.COMBO_TEXT == {'TRW_TrackSortCombobox': 'Distance', 'TRW_TrackPlayersCombobox': 'On'}
    for screen_id, *_ in skin.TRACK_FILTERS:
        middle = skin.FILTER_SIZE // 2
        assert region(screen_id).getpixel((middle, middle)) != region(screen_id).getpixel((2, middle)), screen_id


def test_preview_fills_in_the_aa_window(tmp_path):
    # One look per tab, each with its tab lit and its list's sample rows, a name, rank and cost on each; the description,
    # the points, the % to AA and the timer in the column. The widest name any tab lists fits a padding before the rank.
    preview = preview_module()
    images = preview.Preview(files(), eq_dir=tmp_path).render(skin.AA_FILE)
    assert len(images) == len(skin.AA_PAGES)
    _, _, found = aa_parts()
    (_, name_width), (_, rank_width), (_, cost_width) = skin.AA_COLUMNS
    b = skin.BORDER

    def crop(image, x, y, width, height):
        return image.crop((b + x, b + y, b + x + width, b + y + height))

    def ink(image, left, width, row):
        top = skin.PAGE_TOP + skin.RAID_HEADER_HEIGHT + row * skin.TEXT_HEIGHT
        part = crop(image, skin.LEFT + left, top, width, skin.TEXT_HEIGHT)
        return any(min(p[:3]) > 150 for p in pixels(part))

    for n, (image, (_, list_id, _, _)) in enumerate(zip(images, skin.AA_PAGES)):
        rows = preview.LIST_ROWS[list_id]
        assert 0 < len(rows) <= skin.AA_ROWS
        for row in range(len(rows)):
            assert ink(image, 0, name_width, row) and ink(image, name_width, rank_width, row), (list_id, row)
            assert ink(image, name_width + rank_width, cost_width, row), (list_id, row)
        # The open tab differs from the same tab while another page is open; both land at TOGGLES_TOP.
        tab = crop(image, skin.AA_TAB_LEFTS[n], skin.TOGGLES_TOP, skin.AA_TAB_WIDTHS[n], skin.TOGGLE_SIZE)
        other = crop(images[(n + 1) % len(images)], skin.AA_TAB_LEFTS[n], skin.TOGGLES_TOP, skin.AA_TAB_WIDTHS[n],
                     skin.TOGGLE_SIZE)
        assert tab.tobytes() != other.tobytes(), list_id
    image = images[0]
    panel = image.getpixel((b + skin.AA_COLUMN_X + 2, b + skin.AA_BUTTONS_TOP - skin.PADDING))

    def inked(key):
        return any(p != panel for p in pixels(crop(image, *box(found[key]))))

    for key in ('Description', 'ExpCount', 'CurrentCount', 'TotalCount', 'Timer'):
        assert inked(key), key
    widest = 'Spell Casting Reinforcement Mastery'
    assert widest in {row[0] for rows in preview.LIST_ROWS.values() for row in rows}
    if not any(Path(path).is_file() for path in preview.ARIAL):
        pytest.skip('no Arial to draw font 3 with')
    assert preview.text_mask(widest, skin.TEXT_FONT).getbbox()[2] <= name_width - skin.PADDING
    # Each count's caption fits its box, a padding clear of a three-digit count, and the box holds four digits.
    assert preview.text_mask('0000', skin.TEXT_FONT).getbbox()[2] <= skin.AA_VALUE_WIDTH
    digits = preview.text_mask('000', skin.TEXT_FONT).getbbox()[2]
    for caption_id, caption, _ in skin.AA_NUMBERS:
        width = preview.text_mask(caption, skin.TEXT_FONT).getbbox()[2]
        assert width <= box(found[caption_id])[2] and width + skin.PADDING <= skin.AA_COLUMN_WIDTH - digits, caption
    # The timer's caption and its longest time fit the column.
    for text in (skin.AA_TIMER_CAPTION, '00:00:00'):
        assert preview.text_mask(text, skin.TEXT_FONT).getbbox()[2] <= skin.AA_COLUMN_WIDTH, text


def test_preview_fills_in_the_friends_window(tmp_path):
    # One look per tab, each with its tab lit and its list's sample names from the top of the page, which starts where
    # its page border puts it (see LIST_PAGE_BORDER), and the friends' tab's sample name in its field.
    preview = preview_module()
    images = preview.Preview(files(), eq_dir=tmp_path).render(skin.FRIENDS_FILE)
    assert len(images) == len(skin.FRIENDS_PAGES)
    b = skin.BORDER

    def crop(image, x, y, width, height):
        return image.crop((b + x, b + y, b + x + width, b + y + height))

    def inked(image, x, y, width, height):
        return any(min(p[:3]) > 150 for p in pixels(crop(image, x, y, width, height)))

    names_width = skin.FRIENDS_CONTENT_WIDTH - skin.SCROLL_WIDTH
    field_top = skin.LIST_PAGE_TOP + skin.FRIENDS_FIELD_TOP
    for n, (image, (_, _, list_id, field_id, *_)) in enumerate(zip(images, skin.FRIENDS_PAGES)):
        rows = preview.LIST_ROWS[list_id]
        assert 0 < len(rows) < skin.FRIENDS_ROWS
        for row in range(skin.FRIENDS_ROWS):
            top = skin.LIST_PAGE_TOP + row * skin.TEXT_HEIGHT
            assert inked(image, skin.LEFT, top, names_width, skin.TEXT_HEIGHT) == (row < len(rows)), (list_id, row)
        # Inside the field's outline.
        typed = inked(image, skin.LEFT + skin.FIELD_PADDING, field_top + 1,
                      skin.FRIENDS_FIELD_WIDTH - 2 * skin.FIELD_PADDING, skin.INPUT_HEIGHT - 2)
        assert typed == (field_id in preview.EDIT_TEXT), field_id
        # The open tab differs from the same tab while the other page is open; both land at TOGGLES_TOP.
        spot = (skin.FRIENDS_TAB_LEFTS[n], skin.TOGGLES_TOP, skin.FRIENDS_TAB_WIDTHS[n], skin.TOGGLE_SIZE)
        assert crop(image, *spot).tobytes() != crop(images[1 - n], *spot).tobytes(), list_id


def test_preview_picks_windows_by_words_from_their_file_names():
    preview = preview_module()
    assert preview.chosen([]) == list(skin.WINDOW_FILES)
    assert preview.chosen(['quantity', 'ITEM']) == [skin.ITEM_FILE, skin.QUANTITY_FILE]
    with pytest.raises(SystemExit):
        preview.chosen(['nothing'])


def test_preview_draws_the_spell_icons_from_our_sheets(tmp_path):
    # Spell icons come from our grid animations, cell by cell as the client reads them; the icons sheet shows every
    # drawn cell at 40 and 24 (and 40 scaled to 16), beside another skin's own when comparing, then each plain tile.
    preview = preview_module()
    drawer = preview.Preview(files(), eq_dir=tmp_path)
    for cell in (0, 99, skin.SPELL_ICON_CELLS - 1):
        assert pixels(drawer.grid_cell('A_SpellIcons', cell)) == pixels(spell_icon(cell))
    for cell in (0, 117, skin.GEM_ICON_CELLS - 1):
        assert pixels(drawer.grid_cell('A_SpellGems', cell)) == pixels(spell_icon(cell, skin.GEM_ICON))
    assert drawer.grid_cell('A_SpellIcons', skin.SPELL_ICON_CELLS) is None
    other = tmp_path / 'other'
    other.mkdir()
    sheet = Image.new('RGBA', (skin.ICON_SHEET, skin.ICON_SHEET))
    sheet.paste((255, 0, 0, 255), (40, 0, 80, 40))  # cell 1
    sheet.save(other / 'Spells01.tga')
    gems = Image.new('RGBA', (skin.ICON_SHEET, skin.ICON_SHEET))
    gems.paste((0, 255, 0, 255), (0, 216, 24, 240))  # cell 190, past the 40px cells
    gems.save(other / 'gemicons02.tga')
    assert set(pixels(preview.compare_cell(other, 1))) == {(255, 0, 0, 255)}
    assert set(pixels(preview.compare_cell(other, 190))) == {(0, 255, 0, 255)}
    assert preview.compare_cell(other, 40) is None  # no spells02.tga there
    image = drawer.spell_icon_sheet(other, scale=1)
    margin = preview.MARGIN
    block = 2 * skin.BOOK_ICON + skin.GEM_ICON + skin.ROW_ICON + 4 * margin
    entries = len(skin.SPELL_PICTURES) + sum(any(c not in skin.SPELL_PICTURES for c in group)
                                             for group in skin.SPELL_TILE_CELLS.values())
    assert image.size == (6 * block + margin, -(-entries // 6) * (skin.BOOK_ICON + 2 * margin) + margin)
    first = min(skin.SPELL_PICTURES)
    x = margin + skin.BOOK_ICON + margin  # after the other skin's picture
    drawn = image.crop((x, margin, x + skin.BOOK_ICON, margin + skin.BOOK_ICON))
    assert all(d == i for d, i in zip(pixels(drawn), pixels(spell_icon(first))) if i[3] == 255)


# Releases (tools/release.py)

REPO = Path(__file__).resolve().parent.parent


@functools.cache
def release_module():
    spec = importlib.util.spec_from_file_location('release', REPO / 'tools' / 'release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def commit(**changes):
    """A commit that passes every rule, with changes."""
    release = release_module()
    good = release.Commit('a' * 40, *release.IDENTITY, '2026-09-28 10:00:00 +0000', *release.IDENTITY,
                          '2026-09-28 10:00:00 +0000', 'Add the give window\n\n1. README and CLAUDE.md describe it\n')
    return good._replace(**changes)


def test_the_version_is_on_the_readmes_tagline():
    release = release_module()
    assert re.fullmatch(r'\d+\.\d+\.\d+', skin.VERSION)
    assert release.readme_version((REPO / 'README.md').read_text(encoding='utf-8')) == skin.VERSION
    assert release.source_version((REPO / 'build_skin.py').read_text(encoding='utf-8')) == skin.VERSION
    # Only the tagline counts, the first line under the heading.
    assert release.readme_version('# TriageUI\n\nSkin · by Sebik\n\nSkin · v1.0.0 · by Sebik\n') is None


def test_a_release_is_cut_from_dev_with_everything_committed():
    release = release_module()
    assert release.state_problems('dev', '') == []
    assert len(release.state_problems('main', ' M README.md\n')) == 2


def test_the_version_goes_up_and_is_on_the_readme():
    release = release_module()
    readme = '# TriageUI\n\nSkin · v1.2.0 · by Sebik\n'
    assert release.version_problems('1.2.0', readme, []) == []
    assert release.version_problems('1.2.0', readme, ['v1.0.0', 'v1.1.0', 'wip']) == []
    [tagged] = release.version_problems('1.2.0', readme, ['v1.2.0'])
    assert 'already tagged' in tagged
    [below] = release.version_problems('1.2.0', readme, ['v1.10.0'])  # by number, not by text
    assert 'below the latest tag' in below
    [readme_problem] = release.version_problems('1.3.0', readme, ['v1.2.0'])
    assert readme_problem.startswith('README.md') and 'v1.2.0, not v1.3.0' in readme_problem
    assert 'isn\'t X.Y.Z' in release.version_problems('1.3', readme, [])[0]


def test_commits_carry_only_the_noreply_identity_with_utc_dates():
    release = release_module()
    assert release.identity_problems([commit()]) == []
    problems = release.identity_problems([commit(author_email='someone@work.example',
                                                 committer_date='2026-09-28 13:00:00 +0300')])
    assert len(problems) == 2
    assert 'the author isn\'t CopperGlade' in problems[0] and 'the committer date isn\'t UTC' in problems[1]
    assert 'work.example' not in ''.join(problems)  # the real identity is never printed


def test_no_commit_credits_an_ai():
    release = release_module()
    assert release.attribution_problems([commit()]) == []  # naming CLAUDE.md is fine
    for trailer in ('Co-Authored-By: Someone <noreply@anthropic.com>',
                    '🤖 Generated with [Claude Code](https://claude.com/claude-code)'):
        assert len(release.attribution_problems([commit(message=f'Fix a window\n\n{trailer}\n')])) == 1


def test_only_our_own_files_are_tracked():
    release = release_module()
    assert release.tracked_problems(['.gitignore', 'README.md', 'build_skin.py', 'tests/conftest.py',
                                     'tools/release.py']) == []
    theirs = ['CLAUDE.md', 'notes/client.md', 'build/preview/EQUI_TargetWindow.png', 'dist/TriageUI-v1.0.0.zip',
              'window_pieces01.tga', 'EQUI_Inventory.xml', 'art/Icons.DDS', 'art/splash.bmp']
    assert len(release.tracked_problems(theirs)) == len(theirs)


def test_character_names_come_from_the_everquest_folders_character_files(tmp_path):
    release = release_module()
    for name in ['UI_Zorvak_pq.proj.ini', 'BZR_Quillbank_pq.proj.ini', 'Talmir_pq.proj.ini', 'Brenna_spellsets.ini',
                 'UI_Sebik_pq.proj.ini', 'Sebik_spellsets.ini', 'eqclient.ini', 'zeal.ini', 'Talmir_pq.proj.ini.bak']:
        (tmp_path / name).write_text('')
    assert release.character_names(tmp_path) == {'zorvak', 'quillbank', 'talmir', 'brenna'}


def test_character_names_are_found_as_words_and_never_printed():
    release = release_module()
    second = release.second_player((REPO / 'tests' / 'conftest.py').read_text())
    assert second == 'mera'
    texts = {
        'README.md': 'Zorvak casts\ncamera zorvakian\nUI_Zorvak_pq.proj.ini',
        'tests/test_x.py': 'Mera and Mera\nMera and zorvak',
        'tools/x.py': 'Mera',
        'commit abc1234': 'Fix a window\n\nfor ZORVAK',
    }
    problems = release.name_problems(texts, {'zorvak', second}, second)
    assert [problem.rsplit(':', 1)[0] for problem in problems] == [
        'README.md:1', 'README.md:3', 'tests/test_x.py:2', 'tools/x.py:1', 'commit abc1234:3']
    assert not re.search('zorvak|mera', ' '.join(problems), re.I)
    assert release.name_problems(texts, set()) == []


def test_nothing_mentions_playing_several_characters_at_once():
    release = release_module()
    # Built from parts, so this file doesn't trip the check itself.
    words = ['multi' + 'box', 'Multi-' + 'box' + 'ing', 'box' + 'ing', 'dual ' + 'box', 'box' + 'ers']
    texts = {'README.md': '\n'.join(['the close box', 'a tab box', 'the dialog box', 'two boxes', 'a boxed set', *words])}
    assert [problem.split(':')[1] for problem in release.boxing_problems(texts)] == ['6', '7', '8', '9', '10']


def test_the_release_zip_is_the_built_skin_in_a_triageui_folder(eq, tmp_path):
    # Players drag the zip's TriageUI folder into uifiles: it holds exactly what the given builder writes on default,
    # and nothing of the base's.
    release = release_module()
    assert release.zip_name('1.2.0') == 'TriageUI-v1.2.0.zip'
    out = release.build_zip((REPO / 'build_skin.py').read_text(encoding='utf-8'), eq, tmp_path / 'release.zip')
    built = skin.build(eq, out=tmp_path / 'built' / skin.SKIN_NAME)
    with zipfile.ZipFile(out) as archive:
        assert archive.namelist() == sorted(f'TriageUI/{path.name}' for path in built.iterdir())
        assert {f'TriageUI/{skin.MARKER_FILE}', f'TriageUI/{skin.ANIMATIONS_FILE}'} <= set(archive.namelist())
        assert not {f'TriageUI/{KEPT_FILE}', 'TriageUI/window_pieces01.tga'} & set(archive.namelist())
        for path in built.iterdir():
            assert archive.read(f'TriageUI/{path.name}') == path.read_bytes()
