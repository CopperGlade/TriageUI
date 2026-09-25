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
LOAD_ORDER = [skin.ANIMATIONS_FILE, skin.GROUP_FILE, skin.TARGET_FILE, skin.CASTING_FILE, skin.CHAT_FILE,
              skin.PET_WINDOW_FILE, skin.SELECTOR_FILE, skin.BUFF_FILE, skin.SONG_FILE, skin.PLAYER_FILE]


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
                                  'triageui_field.tga', 'triageui_gutter.tga', 'triageui_dot.tga'])
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
    # The target's bar and %, the casting bar, your pet's bar and %, each group member, pet and %, and
    # the Player window's HP, mana and server tick.
    assert len(gauges) == 5 + 3 * skin.GROUP_SIZE + 3
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
    # Each labeled button size in use has its own art (the selector's icon toggles have theirs).
    buttons = [b for b in buttons if b.find('Text') is not None]
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
    labeled = [b for b in root.iter('Button') if b.find('Text') is not None and box(b)[2:] != (0, 0)]
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
    # Every glyph is 7 rows of one width, sitting on the last row.
    for letter, rows in skin.LABEL_GLYPHS.items():
        assert len(rows) == skin.LABEL_HEIGHT and len({len(r) for r in rows}) == 1, letter
        assert '#' in rows[-1], letter


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
    references += [e.text for tag in ('GaugeDrawTemplate', 'ButtonDrawTemplate') for t in root.iter(tag) for e in t]
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
    # Everything a window or its clips show is defined earlier in the window's own file.
    for name in skin.WINDOW_FILES:
        file_root, window = screen(name)
        assert window.find('DrawTemplate').text == skin.FRAME_TEMPLATE
        defined = set()
        for element in file_root:
            for piece in element.findall('Pieces'):
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
                     'BuffWindow', 'ShortDurationBuffWindow', 'PlayerWindow'}
    # The two slot backgrounds the client paints by name are redefined on purpose, and the base's own
    # definitions taken out, so each name is still defined once.
    allowed = stock_windows | {skin.FRAME_TEMPLATE, skin.FIELD_TEMPLATE, skin.DOT_TEMPLATE, *skin.REPLACED_ANIMATIONS}
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
    for element in list(root.iter('Label')) + list(root.iter('Gauge')):
        assert rgb(element, 'TextColor') == skin.TEXT_RGB
    # The name has the whole first line for long mob names, with the usual padding each side.
    assert box(name)[0] + skin.BORDER == skin.PADDING
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
    assert rgb(gauge, 'FillTint') == skin.TEXT_RGB


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
    for g in everything().iter('Gauge'):
        if (g.get('item').startswith('TUI_') and not g.get('item').startswith(('TUI_GW_PetGauge', 'TUI_PW_'))
                and g.find('GaugeDrawTemplate/Fill') is not None):
            assert rgb(g, 'FillTint') == skin.TEXT_RGB


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
    assert disband[0] - (invite[0] + invite[2]) == skin.BUTTON_GAP == skin.PADDING and invite[2] == disband[2]
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
    # The group window is 20% narrower than the others (the user's call).
    assert skin.GROUP_WIDTH == 160 == box(window)[2]
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
    # pet's health) ending where the target window's bar does.
    root = everything()
    anims = items(root, 'Ui2DAnimation')
    target = rect_of(anims[parts(root)['TUI_Target_HP'].find('GaugeDrawTemplate/Fill').text])[2]
    for n in range(1, skin.GROUP_SIZE + 1):
        member, pet = parts(root)[f'TUI_GW_Gauge{n}'], parts(root)[f'TUI_GW_PetGauge{n}']
        template = member.find('GaugeDrawTemplate')
        assert [e.tag for e in template] == ['Fill'] and template.findtext('Fill') == 'TUI_Clear'
        assert box(member)[3] == skin.TEXT_HEIGHT and box(pet)[1] == box(member)[1] + skin.TEXT_HEIGHT
        pet_bar = rect_of(anims[pet.find('GaugeDrawTemplate/Fill').text])[2]
        assert box(pet)[0] + number(pet, 'GaugeOffsetX') + pet_bar == skin.LEFT + target == skin.LEFT + skin.GROUP_BAR_WIDTH
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
    # The whole line in a soft red (the user's pick), so the casting window stands apart from the target window.
    assert rgb(spell, 'TextColor') == rgb(prefix, 'TextColor') == skin.SPELL_RGB == (232, 128, 128)
    # The spell name follows "Casting:" and a space, on the same line, to the window's padding.
    assert box(prefix)[0] == skin.LEFT and box(spell)[0] == box(prefix)[0] + box(prefix)[2] == skin.LEFT + 50
    assert box(prefix)[1] == box(spell)[1] == 0
    assert box(spell)[0] + box(spell)[2] == skin.TARGET_RIGHT
    gauge = found['TUI_Casting_Gauge']
    assert gauge.find('EQType').text == '7' and gauge.find('ScreenID').text == 'Gauge'


def test_casting_window_is_the_target_windows_size_with_a_full_width_bar():
    # The same size as the target window, the bar at the height of its health bar, as if there were
    # text on the second line to center it on, but across the whole width (the user's request).
    root = everything()
    cast = parts(root)['TUI_Casting_Gauge']
    health = parts(root)['TUI_Target_HP']
    assert box(cast)[1] == box(health)[1] and box(cast)[3] == box(health)[3]
    assert box(cast)[0] == skin.LEFT and box(cast)[0] + box(cast)[2] == skin.TARGET_RIGHT
    assert box(screen(skin.CASTING_FILE)[1])[2:] == box(screen(skin.TARGET_FILE)[1])[2:]


def test_pet_window_is_the_target_windows_shape_with_its_commands():
    # A pixel wider than the target window, so its three columns of buttons come out even.
    assert skin.PET_WIDTH == skin.TARGET_WIDTH + 1
    root, window = check_inside_frame(skin.PET_WINDOW_FILE, skin.PET_WIDTH)
    everything_root = everything()
    found = parts(root)
    by_id = {e.findtext('ScreenID'): e for e in found.values() if e.findtext('ScreenID')}
    # Your pet's gauge: its own text is the pet's name ("No Pet" until the client sets it) on the first
    # line, and its bar where the target window's is, a pixel longer like the window.
    health = by_id['PetHPGauge']
    assert health.find('EQType').text == '16'
    assert (number(health, 'TextOffsetX'), number(health, 'TextOffsetY')) == (0, 0)
    assert health.find('Text').text == 'No Pet'
    target_bar = box(parts(everything_root)['TUI_Target_HP'])
    x, y, w, h = box(health)
    assert (x + number(health, 'GaugeOffsetX'), y + number(health, 'GaugeOffsetY')) == target_bar[:2]
    assert (w, h - number(health, 'GaugeOffsetY')) == (target_bar[2] + 1, target_bar[3])
    # Its HP number and drawn % on the target's line, ending at the window's padding; at 100% the bar
    # ends a padding's width before the number, as in the target window. The % shows only while you
    # have a pet.
    number_label = by_id['PIW_PetHPLabel']
    assert number_label.find('EQType').text == '69'
    target_number = box(parts(everything_root)['TUI_Target_HPLabel'])
    assert box(number_label) == (target_number[0] + 1, *target_number[1:])
    assert box(number_label)[0] - (x + w) == skin.PADDING
    clips = items(root, 'Screen')
    percent = box(clips['TUI_PIW_HPPercent_Clip'])
    target_percent = box(items(everything_root, 'Screen')['TUI_Target_HPPercent_Clip'])
    assert percent == (target_percent[0] + 1, *target_percent[1:])
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


def test_chat_window_has_no_title_bar_and_resizes():
    # The user: no header needed, everyone knows which window they chat in.
    root, window = screen(skin.CHAT_FILE)
    assert window.get('item') == 'ChatWindow'
    for style in ('Style_Titlebar', 'Style_Closebox', 'Style_Minimizebox'):
        assert window.find(style).text == 'false'
    assert window.find('Style_Sizable').text == 'true' and window.find('Style_Border').text == 'true'
    assert window.find('DrawTemplate').text == skin.FRAME_TEMPLATE
    # The client names each chat window itself.
    assert window.find('Text') is None
    assert box(window)[2:] == skin.CHAT_SIZE


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
    # stopping short of the grab spot, drawn by a child window's background.
    strip = found['TUI_CW_InputStrip']
    assert strip.tag == 'Screen'
    assert anchors(strip) == (skin.LEFT, skin.LEFT + skin.INPUT_HEIGHT, skin.LEFT + skin.GRIP_WIDTH + skin.INPUT_GAP,
                              skin.LEFT)
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
    # Drawn after the strip, so the text is on top of it.
    order = [p.text for p in window.findall('Pieces')]
    assert order.index('TUI_CW_InputStrip') < order.index('TUI_CW_ChatInput')


def test_chat_window_has_a_grab_spot_in_the_bottom_right_corner():
    # With no title bar, the user asked for a small square in a corner to drag the window by. The spot is
    # the window's own background, marked by six dots, each a tiny anchored child window: one child window
    # holding all six showed them but took the drag, and a picture alone showed nothing in game.
    root, window = screen(skin.CHAT_FILE)
    found = {e.get('item'): e for e in direct_pieces(root, window)}
    dots = [found[f'TUI_CW_GripDot{n}'] for n in range(len(skin.GRIP_DOTS))]
    assert len(skin.GRIP_DOTS) == 6 and not [e for e in root.iter('StaticAnimation')]
    covered = set()
    for dot, (dx, dy) in zip(dots, skin.GRIP_DOTS):
        assert dot.tag == 'Screen' and dot.find('ScreenID') is None and dot.findtext('DrawTemplate') == skin.DOT_TEMPLATE
        assert dot.findtext('Style_Border') == 'false' and dot.find('Pieces') is None
        # Pinned to the bottom right: every edge measured from the right or the bottom, 2x2, at its place
        # in the GRIP_WIDTH x INPUT_HEIGHT spot under the scrollbar's column, level with the input line.
        for side in ('LeftAnchorToLeft', 'TopAnchorToTop', 'RightAnchorToLeft', 'BottomAnchorToTop'):
            assert dot.find(side).text == 'false'
        left, top, right, bottom = anchors(dot)
        assert (left - right, top - bottom) == (2, 2)
        spot_x, spot_y = skin.LEFT + skin.GRIP_WIDTH - left, skin.LEFT + skin.INPUT_HEIGHT - top
        assert (spot_x, spot_y) == (dx, dy)
        covered |= {(spot_x + i, spot_y + j) for i in (0, 1) for j in (0, 1)}
    # Centered in the spot, and most of it bare background to drag by.
    xs, ys = [x for x, _ in covered], [y for _, y in covered]
    assert min(xs) + max(xs) == skin.GRIP_WIDTH - 1 and min(ys) + max(ys) == skin.INPUT_HEIGHT - 1
    assert len(covered) * 5 < skin.GRIP_WIDTH * skin.INPUT_HEIGHT
    assert skin.GRIP_WIDTH == skin.SCROLL_WIDTH
    # The input line's strip ends a gap before the spot.
    assert number(found['TUI_CW_InputStrip'], 'RightAnchorOffset') - (skin.LEFT + skin.GRIP_WIDTH) == skin.INPUT_GAP
    # The dot template draws only its background: the dot's soft white.
    template = items(everything(), 'WindowDrawTemplate')[skin.DOT_TEMPLATE]
    assert template.findtext('Background') == skin.DOT_TEXTURE
    assert set(pixels(decode(files()[skin.DOT_TEXTURE]))) == {(255, 255, 255, skin.GRIP_ALPHA)}

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


@pytest.mark.parametrize('name, item, slots, first_type', [
    (skin.BUFF_FILE, 'BuffWindow', 15, 45), (skin.SONG_FILE, 'ShortDurationBuffWindow', 6, 135)])
def test_effects_are_a_table_of_rows_icon_then_name(name, item, slots, first_type):
    # EQ Triage's table look, as the user asked: a row per slot, compact, with a divider between.
    root, window = check_inside_frame(name)
    assert window.get('item') == item
    buttons = [b for b in root.iter('Button')]
    assert [b.findtext('ScreenID') for b in buttons] == [f'Buff{n}' for n in range(slots)]
    names = {e.findtext('ScreenID'): e for e in root.iter('Label')}
    for n, b in enumerate(buttons):
        x, y, w, h = box(b)
        # As wide as the window's inside, so the client, which lays the slots out itself left to right a
        # pixel apart, puts one per row.
        assert (x, y, w, h) == (0, n * skin.ROW_PITCH, box(window)[2] - 2 * skin.BORDER, skin.ROW_HEIGHT)
        assert skin.ROW_PITCH == skin.ROW_HEIGHT + 1
        # The client paints the background and the spell's icon. Zeal's time left sits at the button's
        # top left (it covered the names' first letters in game), so the icon comes a padding after a
        # column for it, a padding from the window's top and bottom.
        assert b.findtext('ButtonDrawTemplate/Normal') == 'BlueIconBackground'
        assert b.findtext('ButtonDrawTemplate/NormalDecal') == skin.BUFF_ICONS
        assert (number(b, 'DecalOffset/X'), number(b, 'DecalOffset/Y')) == (skin.ROW_ICON_X, skin.ROW_ICON_MARGIN)
        # The icon 18px further in than the window's padding (the user's call), 24px from its edge.
        assert skin.BORDER + skin.ROW_ICON_X == skin.PADDING + skin.TIMER_WIDTH == 24
        assert (number(b, 'DecalSize/CX'), number(b, 'DecalSize/CY')) == (skin.ROW_ICON, skin.ROW_ICON)
        assert skin.BORDER + skin.ROW_ICON_MARGIN == skin.PADDING
        # The name a padding after the icon, centered in the row, ending a padding from the edge.
        label = names[f'Buff{n}Label']
        lx, ly, lw, lh = box(label)
        assert label.findtext('EQType') == str(first_type + n) and not label.findtext('Text')
        assert lx == skin.ROW_ICON_X + skin.ROW_ICON + skin.PADDING and lx + lw == skin.RIGHT
        assert ly - y == (skin.ROW_HEIGHT - lh) // 2
    # A divider in each pixel between rows, as long as the bars, softer than the bars' track (the user).
    dividers = [box(e) for e in root.iter('StaticAnimation')]
    assert dividers == [(skin.LEFT, n * skin.ROW_PITCH - 1, skin.BAR_WIDTH, 1) for n in range(1, slots)]
    assert {e.findtext('Animation') for e in root.iter('StaticAnimation')} == {'TUI_RowDivider'}
    line = cut(decode(files()[skin.PIECES_TEXTURE]), items(everything(), 'Ui2DAnimation')['TUI_RowDivider'])
    assert set(pixels(line)) == {skin.ROW_DIVIDER_RGBA} and skin.ROW_DIVIDER_RGBA[3] < skin.EDGE_FADED[3]
    assert box(window)[3] == 2 * skin.BORDER + slots * skin.ROW_PITCH - 1
    # The slot buttons are the window's last pieces, over the names, so a click anywhere on a row
    # reaches the slot and clicks the effect off (the user couldn't with the names on top).
    order = [p.text for p in window.findall('Pieces')]
    first_button = min(order.index(b.get('item')) for b in buttons)
    assert all(order.index(e.get('item')) < first_button for e in root.iter('Label'))
    assert order[-slots:] == [b.get('item') for b in buttons]


def test_player_window_shows_hp_mana_and_resists_only():
    # The user wanted only the HP and mana bars and values and the resists, abbreviated.
    root, window = check_inside_frame(skin.PLAYER_FILE)
    assert window.get('item') == 'PlayerWindow'
    by_id = {e.findtext('ScreenID'): e for e in parts(root).values() if e.findtext('ScreenID')}
    labels = {e.get('item'): e for e in root.iter('Label')}
    # The four gauges the client looks up; stamina and pet stay, hidden.
    assert {by_id[i].findtext('EQType') for i in ('PlayerHP', 'PlayerMana')} == {'1', '2'}
    for screen_id, eq_type in (('PlayerFatigue', '3'), ('PetHP', '16')):
        assert by_id[screen_id].findtext('EQType') == eq_type and box(by_id[screen_id])[2:] == (0, 0)
    for n, (screen_id, caption, current_type, max_type) in enumerate((
            ('PlayerHP', 'Health', '17', '18'), ('PlayerMana', 'Mana', '124', '125'))):
        # The user's layout: the caption on the left and current/max on the right of one line, the bar
        # under it as in the group window, the next section a padding under the bar (to the caption's ink).
        top = skin.PLAYER_SECTIONS_TOP + n * skin.PLAYER_SECTION_PITCH
        head = labels[f'TUI_PW_{screen_id}Caption']
        assert head.findtext('Text') == caption and head.findtext('AlignLeft') == 'true'
        assert box(head)[:2] == (skin.LEFT, top) and rgb(head, 'TextColor') == skin.PET_RGB
        # Every part of the value in the game's green: it colors the max HP itself, so the user had all
        # the values match it. The max ends at the window's padding.
        current, slash, most = (labels[f'TUI_PW_{screen_id}{part}'] for part in ('Current', 'Slash', 'Max'))
        assert current.findtext('EQType') == current_type and rgb(current, 'TextColor') == skin.VALUE_RGB == (0, 255, 0)
        assert current.findtext('AlignRight') == 'true'
        assert slash.findtext('Text') == '/' and rgb(slash, 'TextColor') == skin.VALUE_RGB
        assert most.findtext('EQType') == max_type and rgb(most, 'TextColor') == skin.VALUE_RGB
        assert most.findtext('AlignLeft') == 'true'
        cx, cy, cw, ch = box(current)
        sx, sy, sw, sh = box(slash)
        mx, my, mw, mh = box(most)
        assert cy == sy == my == top and cx + cw == sx and sx + sw == mx and mx + mw == skin.RIGHT
        assert cw == mw == skin.PLAYER_NUMBER_WIDTH and box(head)[0] + box(head)[2] <= cx
        # A space either side of the slash, so the numbers read apart (the user's request).
        assert sw == 4 + 2 * skin.SPACE_WIDTH and slash.findtext('AlignCenter') == 'true'
        bar = box(by_id[screen_id])
        assert bar == (skin.LEFT, top + skin.BAR_TOP, skin.BAR_WIDTH, skin.BAR_HEIGHT)
        if n:
            above = box(by_id['PlayerHP'])
            assert top + skin.TEXT_INK_TOP - (above[1] + above[3]) >= skin.PADDING
            assert top + skin.TEXT_INK_TOP - (above[1] + above[3]) < skin.PADDING + 1
    # Mana's bar a soft blue (the user's pick); HP's in the usual color.
    assert rgb(by_id['PlayerMana'], 'FillTint') == skin.MANA_RGB and rgb(by_id['PlayerHP'], 'FillTint') == skin.TEXT_RGB
    # The resists: a grey caption over each number, in five columns across the window.
    columns = []
    for caption, eq_type in skin.RESISTS:
        head, number_label = labels[f'TUI_PW_{caption}Caption'], labels[f'TUI_PW_{caption}']
        assert head.findtext('Text') == caption and rgb(head, 'TextColor') == skin.PET_RGB
        assert head.findtext('Font') == '2' and head.findtext('AlignCenter') == 'true'
        assert number_label.findtext('EQType') == str(eq_type) and number_label.findtext('AlignCenter') == 'true'
        assert rgb(number_label, 'TextColor') == skin.VALUE_RGB  # the values' green (the user's call)
        hx, hy, hw, hh = box(head)
        assert box(number_label) == (hx, hy + hh, hw, skin.TEXT_HEIGHT)
        columns.append((hx, hw))
    assert [c for c, _ in skin.RESISTS] == ['DR', 'PR', 'MR', 'FR', 'CR']
    assert columns[0][0] == skin.LEFT and columns[-1][0] + columns[-1][1] == skin.RIGHT
    assert all(a[0] + a[1] == b[0] for a, b in zip(columns, columns[1:]))
    # The resist captions' ink two paddings under the mana bar (the user asked for 6px more).
    mana_bar = box(by_id['PlayerMana'])
    assert box(labels['TUI_PW_DRCaption'])[1] + skin.CAPTION_INK_TOP - (mana_bar[1] + mana_bar[3]) == 2 * skin.PADDING
    # The window's bottom edge a padding under the resists' numbers' ink (the drawn %'s bottom).
    numbers = box(labels['TUI_PW_DR'])
    ink_bottom = skin.BORDER + numbers[1] + skin.PERCENT_INK_TOP + skin.PERCENT_GLYPH_HEIGHT
    assert box(window)[3] - ink_bottom == skin.PADDING
    # Your name on the first line (the user's request), the rest straight under it.
    name = labels['TUI_PW_Name']
    assert name.findtext('EQType') == '1' and box(name)[0::2] == (skin.LEFT, skin.BAR_WIDTH)
    assert rgb(name, 'TextColor') == skin.TEXT_RGB and name.findtext('AlignLeft') == 'true'
    # 6px more under the name (the user's request).
    assert box(labels['TUI_PW_PlayerHPCaption'])[1] == box(name)[1] + skin.TEXT_HEIGHT + skin.PADDING
    # Zeal's server tick along the top of the inside (in the frame it didn't show), as long as the
    # content, and the name's ink a padding under it.
    tick = by_id['ZealTick']
    assert tick.findtext('EQType') == '24'
    assert box(tick) == (skin.LEFT, 0, skin.BAR_WIDTH, skin.TICK_HEIGHT)
    gap = box(name)[1] + skin.TEXT_INK_TOP - skin.TICK_HEIGHT
    assert skin.PADDING <= gap < skin.PADDING + 1
    # Nothing else: no stamina, experience or other stats.
    assert len(labels) == 1 + 2 * 4 + 2 * len(skin.RESISTS)


def test_slot_backgrounds_are_redefined_clear_and_a_faint_red():
    # The client paints helpful effects with BlueIconBackground and harmful ones with RedIconBackground:
    # the skin's are clear and a faint red row, inset like the dividers, replacing the base's own.
    data = files()[skin.ANIMATIONS_FILE].decode('latin-1')
    assert data.count('item="BlueIconBackground"') == data.count('item="RedIconBackground"') == 1
    anims = items(parse(skin.ANIMATIONS_FILE), 'Ui2DAnimation')
    atlas = decode(files()[skin.PIECES_TEXTURE])
    # A whole row that looks like the panel but isn't clear: a button seems to let clicks through its
    # art's clear pixels, and effects couldn't be clicked off with a clear one in game.
    blue = cut(atlas, anims['BlueIconBackground'])
    assert blue.size == (skin.ROW_WIDTH, skin.ROW_HEIGHT)
    assert set(pixels(blue)) == {skin.HELPFUL_RGBA} == {(*skin.PANEL_RGBA[:3], skin.STEP)}
    red = cut(atlas, anims['RedIconBackground'])
    assert red.size == (skin.ROW_WIDTH, skin.ROW_HEIGHT)
    middle = skin.ROW_HEIGHT // 2
    assert red.getpixel((skin.LEFT, middle)) == skin.HARMFUL_RGBA and red.getpixel((skin.LEFT - 1, middle))[3] == 0
    assert red.getpixel((skin.ROW_WIDTH - skin.LEFT - 1, middle)) == skin.HARMFUL_RGBA
    assert red.getpixel((skin.ROW_WIDTH - skin.LEFT, middle))[3] == 0
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
    # duxaUI's player window defines the animation Blackbox, which its hot button window uses: after our
    # player window replaced theirs, the client reported it missing. Such definitions move into our
    # animations file; ones nothing else uses don't, nor the replaced window itself.
    base = eq / 'uifiles' / 'duxaUI'
    blackbox = ('<Ui2DAnimation item="Blackbox">\r\n    <Cycle>true</Cycle>\r\n'
                '    <Frames><Texture>window_pieces22.tga</Texture></Frames>\r\n  </Ui2DAnimation>')
    (base / 'EQUI_PlayerWindow.xml').write_bytes((
        '<XML>\r\n  ' + blackbox + '\r\n'
        '  <Ui2DAnimation item="OnlyHere"><Cycle>true</Cycle></Ui2DAnimation>\r\n'
        '  <StaticAnimation item="PW_Box"><Animation>Blackbox</Animation></StaticAnimation>\r\n'
        '  <Screen item="PlayerWindow"><Pieces>PW_Box</Pieces></Screen>\r\n</XML>\r\n').encode())
    (base / 'EQUI_HotButtonWnd.xml').write_text('<XML><StaticAnimation item="HB"><Animation>Blackbox</Animation>'
                                               '</StaticAnimation></XML>')
    out = skin.build(eq)
    animations = (out / skin.ANIMATIONS_FILE).read_bytes().decode('latin-1')
    assert animations.count('item="Blackbox"') == 1 and 'OnlyHere' not in animations and 'PW_Box' not in animations
    assert '\n' not in animations.replace('\r\n', '')
    root = ET.fromstring(animations.split('\n', 1)[1])
    assert items(root, 'Ui2DAnimation')['Blackbox'].findtext('Frames/Texture') == 'window_pieces22.tga'
    # Before our own definitions, inside the file.
    assert animations.index('item="Blackbox"') < animations.index(f'item="{skin.FRAME_TEMPLATE}"')


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
