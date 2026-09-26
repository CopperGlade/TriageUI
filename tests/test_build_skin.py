import functools
import io
import os
import re
import xml.etree.ElementTree as ET
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
              skin.CHAT_FILE, skin.PET_WINDOW_FILE, skin.ACTIONS_FILE, skin.SELECTOR_FILE, skin.HOTBUTTON_FILE,
              skin.BUFF_FILE, skin.SONG_FILE, skin.PLAYER_FILE, skin.BREATH_FILE, skin.RAID_FILE]


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


def parts(root):
    return {e.get('item'): e for tag in ('Gauge', 'Label', 'Button') for e in root.iter(tag)}


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
                                  'triageui_field.tga', 'triageui_gutter.tga'])
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
    # where the rows stay full width for clicking and the bars are as long as the target window's.
    root = everything()
    anims = items(root, 'Ui2DAnimation')
    # Not the hidden ones, which have no size.
    gauges = [g for g in root.iter('Gauge') if g.get('item').startswith('TUI_') and box(g)[2:] != (0, 0)]
    # The server tick, the target's bar and %, the casting bar, your pet's bar and %, each group member,
    # pet and %, the Player window's HP and mana with their %s and its XP/hour's %, the spell bar's recast bars
    # and global recovery, and the air bar.
    assert len(gauges) == 6 + 3 * skin.GROUP_SIZE + 5 + skin.GEM_COUNT + 1 + 1
    for g in gauges:
        if g.find('GaugeDrawTemplate/Fill') is None or g.find('GaugeDrawTemplate/Fill').text == 'TUI_PercentSign':
            continue  # shown whole or not at all, not a bar: see the % and empty slot tests
        if g.get('item').startswith('TUI_GW_Gauge'):
            continue  # no bar, only the member's name: see the group tests
        x, y, width, height = box(g)
        bar = (width - number(g, 'GaugeOffsetX'), height - number(g, 'GaugeOffsetY', 16))
        if g.get('item').startswith('TUI_GW_PetGauge'):
            bar = (skin.GROUP_BAR_WIDTH - skin.PET_INDENT, bar[1])
        template = g.find('GaugeDrawTemplate')
        fill = skin.WHITE if g.get('item').startswith('TUI_GW_PetGauge') else skin.BAR_FILL
        if g.get('item') == 'TUI_Target_ZealTick':
            fill = skin.EDGE_FADED  # see the server tick test
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
    # Not the hidden ones, nor the effect slots, which the client paints (see the effects tests).
    buttons = [b for b in root.iter('Button')
               if box(b)[2:] != (0, 0) and b.find('ButtonDrawTemplate/NormalDecal') is None]
    assert buttons
    for b in buttons:
        template = b.find('ButtonDrawTemplate')
        assert [e.tag for e in template] == list(skin.BUTTON_STATES)
        for state in template:
            assert cut(atlas, anims[state.text]).size == box(b)[2:]
    # Each labeled button size in use has its own art (the selector's icon toggles have theirs, and the hot button
    # window's macros their own solid art: see its tests).
    buttons = [b for b in buttons if b.find('Text') is not None
               and not b.findtext('ButtonDrawTemplate/Normal').startswith('TUI_HotButton')]
    assert {box(b)[2:] for b in buttons} == set(skin.BUTTON_LABELS)
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
    labeled = [b for b in root.iter('Button')
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
    # Every glyph is 7 rows of one width, sitting on the 7th, but the space, which has no ink, and p, whose stem
    # goes a row below (on the line, it read as a small capital P).
    for letter, rows in skin.LABEL_GLYPHS.items():
        assert len(rows) == skin.LABEL_HEIGHT + (letter == 'p') and len({len(r) for r in rows}) == 1, letter
        assert ('#' in rows[skin.LABEL_HEIGHT - 1]) != (letter == ' '), letter
    assert skin.LABEL_TOP + skin.LABEL_HEIGHT + 1 < skin.BUTTON_HEIGHT - 1  # the stem clears the button's edge
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
    art = {state.text for b in root.iter('Button') for state in b.find('ButtonDrawTemplate')} - {'TUI_Clear',
                                                                                                  skin.BUFF_ICONS}
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
    # The spell icons are the stock ones (see the stock names test).
    for name in set(references) - {skin.BUFF_ICONS}:
        assert name in anims, name
    references += [e.text for e in root.iter('Animation')]
    for name in set(references) - {skin.BUFF_ICONS}:
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
        assert window.find('DrawTemplate').text in (skin.FRAME_TEMPLATE, skin.CHAT_TEMPLATE)
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
                     'HotButtonWnd', 'BreathWindow', 'RaidWindow'}
    # The two slot backgrounds the client paints by name are redefined on purpose, and the base's own
    # definitions taken out, so each name is still defined once.
    allowed = stock_windows | {skin.FRAME_TEMPLATE, skin.CHAT_TEMPLATE, skin.FIELD_TEMPLATE, skin.EDIT_TEMPLATE,
                               *skin.REPLACED_ANIMATIONS}
    assert ours and all(name.startswith('TUI_') or name in allowed or name.endswith('.tga') for name in ours)
    assert len(ours) == len(set(ours))


def stock_animations():
    for folder in EQ_DIRS:
        path = Path(folder) / 'uifiles' / 'default' / 'EQUI_Animations.xml'
        if folder and path.is_file():
            return set(re.findall(r'<Ui2DAnimation item\s*=\s*"([^"]+)"', path.read_text(encoding='latin-1')))
    pytest.skip('no EverQuest folder with uifiles/default here')


def test_stock_names_we_use_exist_in_the_default_skin():
    stock = stock_animations()
    root = everything()
    used = {e.text for e in root.iter() if e.text and e.text.startswith('A_')} | {skin.BUFF_ICONS}
    assert used and used <= stock
    # And the slot backgrounds we redefine are the stock ones the client paints by name.
    assert set(skin.REPLACED_ANIMATIONS) <= stock


# The windows

def check_inside_frame(name, expected_width=skin.WINDOW_WIDTH):
    root, window = screen(name)
    width, height = box(window)[2:]
    assert width == expected_width
    assert window.find('Style_Titlebar').text == 'false'
    inner_width, inner_height = width - 2 * skin.BORDER, height - 2 * skin.BORDER
    for element in direct_pieces(root, window):
        x, y, w, h = box(element)
        assert 0 <= x and x + w <= inner_width and 0 <= y and y + h <= inner_height, element.get('item')
    return root, window


def percent_box(root):
    return box(items(root, 'Screen')['TUI_Target_HPPercent_Clip'])


def without_tick(rect):
    """A rect in the target window as it would be without the server tick above the name, which the
    casting and pet windows don't have."""
    x, y, width, height = rect
    return x, y - skin.TARGET_NAME_TOP, width, height


def test_target_window_shows_name_hp_percent_and_hp_bar():
    # 20% narrower than the other windows, then 10% wider, at the user's requests.
    assert skin.TARGET_WIDTH == 176 == round(skin.WINDOW_WIDTH * 0.8 * 1.1)
    root, window = check_inside_frame(skin.TARGET_FILE, skin.TARGET_WIDTH)
    found = parts(root)
    name, number = found['TUI_Target_Name'], found['TUI_Target_HPLabel']
    assert name.find('EQType').text == '28'
    assert number.find('EQType').text == '29'
    bars = [g for g in root.iter('Gauge') if g.find('ScreenID') is not None]
    assert [g.get('item') for g in bars] == ['TUI_Target_ZealTick', 'TUI_Target_HP']
    assert bars[1].find('EQType').text == '6' and bars[1].find('ScreenID').text == 'TargetHP'
    # The name and number in the text's color (see the target and casting colors test).
    for element in root.iter('Label'):
        assert rgb(element, 'TextColor') == skin.TEXT_RGB
    # Zeal's server tick along the top of the inside (in the frame it didn't show), as wide as the name's
    # line, and the name's ink a padding under it. It moved here from the player window (the user's request).
    tick = bars[0]
    assert tick.findtext('EQType') == '24' and tick.findtext('ScreenID') == 'ZealTick'
    assert box(tick) == (skin.LEFT, 0, box(name)[2], skin.TICK_HEIGHT) and skin.TICK_WIDTH == box(name)[2]
    gap = box(name)[1] + skin.TEXT_INK_TOP - skin.TICK_HEIGHT
    assert skin.PADDING <= gap < skin.PADDING + 1
    assert box(window)[3] == skin.TARGET_NAME_TOP + skin.TARGET_HEIGHT
    # The name has the whole first line for long mob names, with the usual padding each side.
    assert box(name)[0] + skin.BORDER == skin.PADDING
    assert skin.TARGET_WIDTH - skin.BORDER - (box(name)[0] + box(name)[2]) == skin.PADDING
    # The number sits straight under the name's line, right-aligned, and the % hugs it.
    assert box(number)[1] == skin.TARGET_NAME_TOP + skin.TARGET_LINE2 == box(name)[1] + box(name)[3]
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
    # (The group window's drawn % is its soft blue: see the group window's test.)
    group_percents = tuple(f'TUI_GW{n}_HPPercent' for n in range(1, skin.GROUP_SIZE + 1))
    for g in everything().iter('Gauge'):
        if (g.get('item').startswith('TUI_')
                and not g.get('item').startswith(('TUI_GW_PetGauge', 'TUI_PW_', 'TUI_Target_ZealTick',
                                                  'TUI_Casting_Gauge', 'TUI_CSPW_Global_Recast', 'TUI_Breath_Gauge',
                                                  *group_percents))
                and g.find('GaugeDrawTemplate/Fill') is not None):
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


def test_server_tick_is_the_other_bars_track_color_with_no_track():
    # The user wanted the tick itself in the color of the other bars' faint track ("shadow"), and no track
    # behind it: a white tint over a fill of exactly the tracks' color.
    root = everything()
    tick = parts(root)['TUI_Target_ZealTick']
    anims = items(root, 'Ui2DAnimation')
    assert rgb(tick, 'FillTint') == skin.TICK_RGB == (255, 255, 255)
    track = colors(anims[parts(root)['TUI_Target_HP'].findtext('GaugeDrawTemplate/Background')])
    assert colors(anims[tick.findtext('GaugeDrawTemplate/Fill')]) == track == {skin.EDGE_FADED}
    assert tick.find('GaugeDrawTemplate/Background') is None
    assert 'TUI_TickTrack' not in anims


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


def test_group_members_are_one_line_with_no_bar_and_pets_keep_a_thin_one():
    # The user wanted just the values, and a shorter window: a member is their name and health % on one
    # line; their pet's line follows straight under it, with a thin bar (the client gives no number for a
    # pet's health) ending where the pet window's bar does (the user's pick; the target's before).
    root = everything()
    anims = items(root, 'Ui2DAnimation')
    pet_window = rect_of(anims[parts(root)['TUI_PIW_PetHPGauge'].find('GaugeDrawTemplate/Fill').text])[2]
    for n in range(1, skin.GROUP_SIZE + 1):
        member, pet = parts(root)[f'TUI_GW_Gauge{n}'], parts(root)[f'TUI_GW_PetGauge{n}']
        template = member.find('GaugeDrawTemplate')
        assert [e.tag for e in template] == ['Fill'] and template.findtext('Fill') == 'TUI_Clear'
        assert box(member)[3] == skin.TEXT_HEIGHT and box(pet)[1] == box(member)[1] + skin.TEXT_HEIGHT
        pet_bar = rect_of(anims[pet.find('GaugeDrawTemplate/Fill').text])[2]
        assert box(pet)[0] + number(pet, 'GaugeOffsetX') + pet_bar == skin.LEFT + pet_window
    assert skin.GROUP_BAR_WIDTH == skin.PIW_BAR_WIDTH == pet_window
    assert skin.MEMBER_PITCH == 39


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
    # The same size as the target window without its server tick, the bar at the height of its health
    # bar, as if there were text on the second line to center it on, but across the whole width (the
    # user's request).
    root = everything()
    cast = parts(root)['TUI_Casting_Gauge']
    health = without_tick(box(parts(root)['TUI_Target_HP']))
    assert box(cast)[1] == health[1] and box(cast)[3] == health[3]
    assert box(cast)[0] == skin.LEFT and box(cast)[0] + box(cast)[2] == skin.TARGET_RIGHT
    width, height = box(screen(skin.TARGET_FILE)[1])[2:]
    assert height - skin.TARGET_NAME_TOP == skin.TARGET_HEIGHT
    assert box(screen(skin.CASTING_FILE)[1])[2:] == (width, skin.TARGET_HEIGHT)


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
    target_bar = without_tick(box(parts(everything_root)['TUI_Target_HP']))
    x, y, w, h = box(health)
    assert (x + number(health, 'GaugeOffsetX'), y + number(health, 'GaugeOffsetY')) == target_bar[:2]
    assert (w, h - number(health, 'GaugeOffsetY')) == (target_bar[2] + shift, target_bar[3])
    # Its HP number and drawn % on the target's line, ending at the window's padding; at 100% the bar
    # ends a padding's width before the number, as in the target window. The % shows only while you
    # have a pet.
    number_label = by_id['PIW_PetHPLabel']
    assert number_label.find('EQType').text == '69'
    target_number = without_tick(box(parts(everything_root)['TUI_Target_HPLabel']))
    assert box(number_label) == (target_number[0] + shift, *target_number[1:])
    assert box(number_label)[0] - (x + w) == skin.PADDING
    clips = items(root, 'Screen')
    percent = box(clips['TUI_PIW_HPPercent_Clip'])
    target_percent = without_tick(box(items(everything_root, 'Screen')['TUI_Target_HPPercent_Clip']))
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
    # thin header, with no name on it (everyone knows which window they chat in) and no boxes.
    root, window = screen(skin.CHAT_FILE)
    assert window.get('item') == 'ChatWindow'
    assert window.find('Style_Titlebar').text == 'true'
    for style in ('Style_Closebox', 'Style_Minimizebox'):
        assert window.find(style).text == 'false'
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
    # Who and Disband, and the socials' bottom two rows (5, 6, 11 and 12), are gone at the user's request, but
    # the client looks them up: no size, clear art.
    hidden = [b for b in root.iter('Button') if box(b)[2:] == (0, 0)]
    assert [b.findtext('ScreenID') for b in hidden] == ['AMP_WhoButton', 'AMP_DisbandButton'] + [
        f'ASP_SocialButton{n}' for n in (5, 6, 11, 12)]
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
    for name, stock in ((skin.TAB_BORDER, STOCK_TAB_BORDER), (skin.PAGE_BORDER, STOCK_PAGE_BORDER)):
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
        # Under the page arrows, the game's columns of six, 1 to 6 then 7 to 12, with the bottom two rows (5, 6,
        # 11 and 12) hidden.
        'ActionsSocialsPage': [(f'ASP_SocialButton{n + 1}', '',
                                (columns[n // 6][0], skin.ARROW_SIZE + skin.PADDING + n % 6 * step, columns[n // 6][1],
                                 height)) for n in range(12) if n % 6 < 4],
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
    # The socials, the tallest page, have five rows with the arrows: the window is no taller (the user's call).
    assert skin.ACTIONS_PAGE_HEIGHT == 5 * step - skin.PADDING


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
               + [(n, skin.ARROW_SIZE, skin.ARROW_SIZE) for n in skin.ARROW_ICONS]
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
    # EQ Triage's table look, as the user asked: a row per slot, compact, with a divider between. 20px wider
    # than the other windows' 200, so longer names fit (the user's call).
    assert skin.EFFECTS_WIDTH == 220
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
        # Across the row but inset like the dividers, so it's narrower than the window's inside: the client
        # lays the slots out itself, a pixel apart, and never hit-tested slots as wide as the inside (no
        # tooltip, no click, no red for harmful effects in game). Two don't fit across, so one per row.
        assert (x, y, w, h) == (skin.LEFT, n * skin.ROW_PITCH, skin.SLOT_WIDTH, skin.ROW_HEIGHT)
        assert skin.SLOT_WIDTH == inside - 2 * skin.LEFT == 208 and 2 * (w + 1) > inside
        assert skin.ROW_PITCH == skin.ROW_HEIGHT + 1
        # The client paints the background and the spell's icon. Zeal's time left sits at the button's
        # top left (it covered the names' first letters in game), so the icon comes a padding after a
        # column for it, a padding from the window's top and bottom.
        assert b.findtext('ButtonDrawTemplate/Normal') == 'BlueIconBackground'
        assert b.findtext('ButtonDrawTemplate/NormalDecal') == skin.BUFF_ICONS
        # The decal offset is within the slot; the icon's place in the window stays ROW_ICON_X.
        assert (x + number(b, 'DecalOffset/X'), number(b, 'DecalOffset/Y')) == (skin.ROW_ICON_X, skin.ROW_ICON_MARGIN)
        # The icon 28px further in than the window's padding (the user's call: at 18 and then 23 Zeal's time
        # box covered some icons), 34px from its edge.
        assert skin.BORDER + skin.ROW_ICON_X == skin.PADDING + skin.TIMER_WIDTH == 34
        assert (number(b, 'DecalSize/CX'), number(b, 'DecalSize/CY')) == (skin.ROW_ICON, skin.ROW_ICON)
        assert skin.BORDER + skin.ROW_ICON_MARGIN == skin.PADDING
        # The name a padding after the icon, centered in the row, ending a padding from the edge.
        label = names[f'Buff{n}Label']
        lx, ly, lw, lh = box(label)
        assert label.findtext('EQType') == str(first_type + n) and not label.findtext('Text')
        assert lx == skin.ROW_ICON_X + skin.ROW_ICON + skin.PADDING and lx + lw == skin.EFFECTS_RIGHT
        assert skin.BORDER + skin.EFFECTS_RIGHT == skin.EFFECTS_WIDTH - skin.PADDING and lw == 158
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
    assert len(drawn) == len(skin.SLOT_ICONS) == 4


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


def test_player_window_shows_hp_mana_xp_per_hour_and_resists_only():
    # The user wanted only the HP and mana bars and values and the resists, abbreviated, then XP/hour.
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
        # In the name's color: the user didn't like the subdued grey the captions had.
        name_color = rgb(labels['TUI_PW_Name'], 'TextColor')
        assert box(head)[:2] == (skin.LEFT, top) and rgb(head, 'TextColor') == skin.CAPTION_RGB == name_color
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
        # right-aligned with the drawn % after it, two paddings before the current number (at one they ran
        # together, and the user asked for the % nearer the caption), in the values' green. The % shows while
        # your own health is above 0, so always. The caption ends before it.
        percent_number = labels[f'TUI_PW_{screen_id}Percent']
        assert percent_number.findtext('EQType') == percent_type and percent_number.findtext('AlignRight') == 'true'
        assert rgb(percent_number, 'TextColor') == skin.VALUE_RGB and not percent_number.findtext('Text')
        px, py, pw, ph = box(percent_number)
        assert py == top and box(head)[0] + box(head)[2] <= px
        percent_clip = items(root, 'Screen')[f'TUI_PW_{screen_id}PercentSign_Clip']
        assert box(percent_clip) == (px + pw, top + skin.PERCENT_INK_TOP, skin.PERCENT_WIDTH,
                                     skin.PERCENT_GLYPH_HEIGHT)
        assert box(percent_clip)[0] + box(percent_clip)[2] + 2 * skin.PADDING == cx
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
    # The resists: a caption in the name's color over each number, in five columns across the window.
    columns = []
    for caption, eq_type in skin.RESISTS:
        head, number_label = labels[f'TUI_PW_{caption}Caption'], labels[f'TUI_PW_{caption}']
        assert head.findtext('Text') == caption and rgb(head, 'TextColor') == rgb(labels['TUI_PW_Name'], 'TextColor')
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
    # paddings under the mana bar (the user asked for it less grouped with Health and Mana), then Zeal's label 81 (a whole percent of a level an hour) with the drawn %
    # after it ending at the window's padding, both in the values' green. The % shows while your own health is
    # above 0, so always.
    mana_bar = box(by_id['PlayerMana'])
    xp_head, xp_number = labels['TUI_PW_ExpPerHourCaption'], labels['TUI_PW_ExpPerHour']
    xp_top = box(xp_head)[1]
    assert xp_head.findtext('Text') == 'XP/hour' and rgb(xp_head, 'TextColor') == skin.CAPTION_RGB
    assert box(xp_head)[0] == skin.LEFT and xp_top == skin.PLAYER_SECTIONS_TOP + 2 * skin.PLAYER_SECTION_PITCH
    assert 2 * skin.PADDING <= xp_top + skin.TEXT_INK_TOP - (mana_bar[1] + mana_bar[3]) < 2 * skin.PADDING + 1
    assert xp_number.findtext('EQType') == '81' and xp_number.findtext('AlignRight') == 'true'
    assert rgb(xp_number, 'TextColor') == skin.VALUE_RGB and not xp_number.findtext('Text')
    nx, ny, nw, nh = box(xp_number)
    assert ny == xp_top and box(xp_head)[0] + box(xp_head)[2] <= nx
    clip = items(root, 'Screen')['TUI_PW_ExpPerHourPercent_Clip']
    assert box(clip) == (nx + nw, xp_top + skin.PERCENT_INK_TOP, skin.PERCENT_WIDTH, skin.PERCENT_GLYPH_HEIGHT)
    assert box(clip)[0] + box(clip)[2] == skin.PLAYER_RIGHT
    percent = items(root, 'Gauge')[clip.find('Pieces').text]
    assert percent.findtext('EQType') == '1' and rgb(percent, 'FillTint') == skin.VALUE_RGB
    # The resist captions' ink two paddings under the XP/hour line's ink (the user asked for 6px more), the
    # same as between the sections above, so the whole window keeps one spacing.
    xp_ink_bottom = xp_top + skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT
    assert box(labels['TUI_PW_DRCaption'])[1] + skin.CAPTION_INK_TOP - xp_ink_bottom == 2 * skin.PADDING
    # The window's bottom edge a padding under the resists' numbers' ink (the drawn %'s bottom).
    numbers = box(labels['TUI_PW_DR'])
    ink_bottom = skin.BORDER + numbers[1] + skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT
    assert box(window)[3] - ink_bottom == skin.PADDING
    # Your name on the first line (the user's request), the rest straight under it.
    name = labels['TUI_PW_Name']
    assert name.findtext('EQType') == '1' and box(name)[0::2] == (skin.LEFT, skin.PLAYER_CONTENT_WIDTH)
    assert rgb(name, 'TextColor') == skin.TEXT_RGB and name.findtext('AlignLeft') == 'true'
    # 6px more under the name (the user's request).
    assert box(labels['TUI_PW_PlayerHPCaption'])[1] == box(name)[1] + skin.TEXT_HEIGHT + skin.PADDING
    # The name at the top like the other windows' first lines: the server tick moved to the target window
    # (the user's request).
    assert box(name)[1] == 0 and 'ZealTick' not in by_id
    # Nothing else: no stamina, experience bar or other stats.
    assert len(labels) == 1 + 2 * 5 + 2 + 2 * len(skin.RESISTS)


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


def test_slot_backgrounds_are_clear_with_a_red_mark_behind_a_harmful_icon():
    # The client paints helpful effects with BlueIconBackground and harmful ones with RedIconBackground,
    # the only sign of an effect's type a skin gets: the skin's are the slot's size (art is drawn at its
    # own size), replacing the base's own. Clear, so the row is the panel at the window's own alpha (solid
    # rows in the panel's color showed as darker stripes at Alpha 205 in game), and a harmful effect's
    # has a red square behind its icon, the row's full height, leaving a 2px ring around the 16px icon
    # (the user's pick over a faint red across the row).
    data = files()[skin.ANIMATIONS_FILE].decode('latin-1')
    assert data.count('item="BlueIconBackground"') == data.count('item="RedIconBackground"') == 1
    anims = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')
    atlas = decode(files()[skin.PIECES_TEXTURE])
    blue = cut(atlas, anims['BlueIconBackground'])
    assert blue.size == (skin.SLOT_WIDTH, skin.ROW_HEIGHT)
    assert set(pixels(blue)) == {skin.HELPFUL_RGBA} == {skin.CLEAR} and skin.CLEAR[3] == 0
    red = cut(atlas, anims['RedIconBackground'])
    assert red.size == (skin.SLOT_WIDTH, skin.ROW_HEIGHT)
    assert skin.snapped(skin.HARMFUL_RGBA) == skin.HARMFUL_RGBA and 0 < skin.HARMFUL_RGBA[3] < 255
    mark = (skin.HARMFUL_MARK_X, 0, skin.HARMFUL_MARK, skin.ROW_HEIGHT)
    assert skin.HARMFUL_MARK == skin.ROW_HEIGHT == skin.ROW_ICON + 2 * skin.ROW_ICON_MARGIN
    for x in range(skin.SLOT_WIDTH):
        for y in range(skin.ROW_HEIGHT):
            inside = mark[0] <= x < mark[0] + mark[2]
            assert red.getpixel((x, y)) == (skin.HARMFUL_RGBA if inside else skin.CLEAR), (x, y)
    # In the window, the square starts a margin before the icon: the icon sits centered in it.
    assert skin.LEFT + skin.HARMFUL_MARK_X == skin.ROW_ICON_X - skin.ROW_ICON_MARGIN
    # Only those two: every other stock definition stays.
    base = BASE_ANIMATIONS.replace('BlueIconBackground', 'SomethingElse')
    assert skin.with_definitions(base, []).count('SomethingElse') == 1


# Building

@pytest.fixture
def eq(tmp_path):
    base = tmp_path / 'uifiles' / 'duxaUI'
    (base / 'Options').mkdir(parents=True)
    (base / 'EQUI_Inventory.xml').write_text('inventory')
    (base / 'eqUI_targetwindow.xml').write_text('their target window')
    (base / 'EQUI_Animations.xml').write_bytes(BASE_ANIMATIONS.encode())
    (base / 'window_pieces01.tga').write_bytes(b'tga')
    (base / 'Options' / 'EQUI_BuffWindow.xml').write_text('option')
    return tmp_path


def test_definitions_only_the_replaced_windows_had_move_to_the_animations(eq):
    # duxaUI's player window defines the animation Blackbox, which its hot button window used: after our
    # player window replaced theirs, the client reported it missing. Such definitions move into our
    # animations file; ones nothing else uses don't, nor the replaced window itself. Our hot button window
    # has since replaced duxaUI's too, so a window we keep stands in for it here.
    base = eq / 'uifiles' / 'duxaUI'
    blackbox = ('<Ui2DAnimation item="Blackbox">\r\n    <Cycle>true</Cycle>\r\n'
                '    <Frames><Texture>window_pieces22.tga</Texture></Frames>\r\n  </Ui2DAnimation>')
    (base / 'EQUI_PlayerWindow.xml').write_bytes((
        '<XML>\r\n  ' + blackbox + '\r\n'
        '  <Ui2DAnimation item="OnlyHere"><Cycle>true</Cycle></Ui2DAnimation>\r\n'
        '  <StaticAnimation item="PW_Box"><Animation>Blackbox</Animation></StaticAnimation>\r\n'
        '  <Screen item="PlayerWindow"><Pieces>PW_Box</Pieces></Screen>\r\n</XML>\r\n').encode())
    (base / 'EQUI_Inventory.xml').write_text('<XML><StaticAnimation item="IW"><Animation>Blackbox</Animation>'
                                            '</StaticAnimation></XML>')
    out = skin.build(eq)
    animations = (out / skin.ANIMATIONS_FILE).read_bytes().decode('latin-1')
    assert animations.count('item="Blackbox"') == 1 and 'OnlyHere' not in animations and 'PW_Box' not in animations
    assert '\n' not in animations.replace('\r\n', '')
    root = ET.fromstring(animations.split('\n', 1)[1])
    assert items(root, 'Ui2DAnimation')['Blackbox'].findtext('Frames/Texture') == 'window_pieces22.tga'
    # Before our own definitions, inside the file.
    assert animations.index('item="Blackbox"') < animations.index(f'item="{skin.FRAME_TEMPLATE}"')


def test_the_spell_bar_keeps_the_base_skins_gem_icons(eq):
    # The client draws a gem's icon from A_SpellGems, by name. The user asked for duxaUI's gems, whose icons
    # differ from the default skin's, so the base's definition and textures stay as they are.
    base = eq / 'uifiles' / 'duxaUI'
    gems = '<Ui2DAnimation item="A_SpellGems"><Frames><Texture>gemicons01.tga</Texture></Frames></Ui2DAnimation>'
    (base / 'EQUI_Animations.xml').write_bytes(BASE_ANIMATIONS.replace('</XML>', f'  {gems}\r\n</XML>').encode())
    (base / 'gemicons01.tga').write_bytes(b'their gem icons')
    (base / skin.CASTSPELL_FILE).write_text('<XML><Screen item="CastSpellWnd" /></XML>')
    out = skin.build(eq)
    animations = (out / skin.ANIMATIONS_FILE).read_bytes().decode('latin-1')
    assert animations.count('item="A_SpellGems"') == 1 and gems in animations
    assert (out / 'gemicons01.tga').read_bytes() == b'their gem icons'
    assert b'CSPW_Spell0' in (out / skin.CASTSPELL_FILE).read_bytes()


def snapshot(folder):
    return {path.relative_to(folder): path.read_bytes() for path in folder.rglob('*') if path.is_file()}


def test_build_copies_the_base_skin_and_adds_ours(eq):
    base = eq / 'uifiles' / 'duxaUI'
    before = snapshot(base)
    out = skin.build(eq)
    assert out == eq / 'uifiles' / 'TriageUI'
    names = {path.name for path in out.iterdir()}
    assert names == {'EQUI_Inventory.xml', 'window_pieces01.tga', skin.MARKER_FILE, *files()}
    assert (out / 'EQUI_Inventory.xml').read_text() == 'inventory'
    for name, data in files().items():
        assert (out / name).read_bytes() == data
    assert snapshot(base) == before


def test_a_base_without_animations_extends_the_default_ones(eq):
    (eq / 'uifiles' / 'duxaUI' / 'EQUI_Animations.xml').unlink()
    default = eq / 'uifiles' / 'default'
    default.mkdir()
    (default / 'equi_animations.xml').write_text('<XML>\n  <Ui2DAnimation item="A_Default" />\n</XML>\n')
    out = skin.build(eq)
    assert 'A_Default' in (out / skin.ANIMATIONS_FILE).read_text()


def test_build_needs_some_animations_file(eq):
    (eq / 'uifiles' / 'duxaUI' / 'EQUI_Animations.xml').unlink()
    with pytest.raises(skin.BuildError, match='Neither duxaUI nor default'):
        skin.build(eq)


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


def test_build_never_writes_into_the_base_skin(eq):
    base = eq / 'uifiles' / 'duxaUI'
    before = snapshot(base)
    with pytest.raises(skin.BuildError, match='must not be the base'):
        skin.build(eq, out=base)
    assert snapshot(base) == before


def test_build_needs_the_base_skin(tmp_path):
    with pytest.raises(skin.BuildError, match='no skin folder'):
        skin.build(tmp_path)


def test_main_reports_success_and_errors(eq, capsys):
    assert skin.main(['--eq', str(eq)]) == 0
    assert '/load TriageUI 1 ' in capsys.readouterr().out
    assert skin.main(['--eq', str(eq), '--base', 'missing']) == 1
    assert 'no skin folder' in capsys.readouterr().err
