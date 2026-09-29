"""Draws TriageUI's windows as PNGs, from the XML and textures the builder makes, with sample names and values, for a
look before going in game.

    python tools/preview.py                every window
    python tools/preview.py quantity item  the windows whose file name contains one of the words

It writes build/preview/<file>.png (--out to change), the window on a backdrop, 3x (--scale). --state draws every
button in another state (Flyby, Pressed, Disabled). Item and spell icons come from the stock skin when an EverQuest
folder is found (EQ_DIR, C:\\QUARM or the Mac mount), grey squares otherwise.

It draws what the XML says the way the client does: the frame, title bar and close box from the window's template,
then each piece in order, clipped to the window's inside. A child Screen clips what it holds, anchored controls take
their place from their anchors, and a TabBox is drawn once per page, stacked. The bag window is sized as the game
sizes it, for the sample bag (BAG), and the compass's strips slid to the sample heading (HEADING). Fonts are Arial stand-ins (12px for font 3, 10 for 2, 9 for 1). The samples show one state of each
window: edit them at the top of this file to check another (the OK-only dialog, a smaller bag).

The builder's files are made in memory (no copy of the base skin) and kept in the output folder until
build_skin.py changes, so only the first preview after a change waits for the atlas.
"""
import argparse
import hashlib
import io
import os
import pickle
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True
import build_skin as skin  # noqa: E402

# Stands in for the base skin's animations file: only TriageUI's own definitions are drawn.
BASE_ANIMATIONS = '<XML ID="EQInterfaceDefinitionLanguage">\n</XML>\n'
EQ_DIRS = [os.environ.get('EQ_DIR', ''), r'C:\QUARM', '/Volumes/[C] Windows 11/QUARM']
DEFAULT_OUT = REPO / 'build' / 'preview'
CACHE_FILE = 'skin-files.pickle'
BACKDROP = (60, 70, 60, 255)  # something like the game behind the window
MARGIN = 12
TITLE_RGB = (192, 192, 192)  # the window's name on its title bar (eqgame.exe's 0xFFC0C0C0; white while active)
STML_RGB = (255, 255, 255)  # an STMLbox has no TextColor; the client's own color is assumed white
PLACEHOLDER_RGBA = (90, 100, 120, 255)  # an icon when no EverQuest folder is found
ARIAL = ['/System/Library/Fonts/Supplemental/Arial.ttf', r'C:\Windows\Fonts\arial.ttf']
FONT_PX = {0: 9, 1: 9, 2: 10, 3: 12, 4: 14, 5: 16, 6: 20}
LINE_HEIGHT = {1: skin.CAPTION_HEIGHT, 2: skin.CAPTION_HEIGHT, 3: skin.TEXT_HEIGHT}
INK_SHIFT = {1: 1, 2: 0, 3: 1}  # lowers Pillow's text to the game's ink tops (TEXT_INK_TOP, CAPTION_INK_TOP)

# Sample data, as the client would fill it in. Labels and gauges by EQType, everything else by ScreenID. The only
# character name allowed in the repo is Sebik; group members go by class, pets by generated pet names.
BUFFS = ['Aegolism', 'Spirit of Wolf', 'Clarity', 'Tashanian', 'Regrowth of Dar Khura', 'Blessing of Temperance',
         'Resist Magic', 'Talisman of Tnarg']
HARMFUL = {'Buff3'}  # the client paints these slots RedIconBackground
SONGS = ["Selo's Accelerando", 'Chant of Battle', "Cassindra's Chorus of Clarity"]
GEMS = ['Complete Healing', 'Divine Aura', 'Superior Healing', 'Symbol of Marzin', 'Resolution', None, 'Root', 'Gate']
GEM_ICONS = [3, 11, 5, 21, 17, None, 30, 44]  # cells of gemicons01.tga
# The hot bar's item and spell spots show only on a hot button holding one: one of each here, the rest macros.
HOT_ITEMS = {'HB_InvSlot3': 20}
HOT_SPELLS = {'HB_SpellGem2': 11}
MERCHANT_ITEMS = 23  # a merchant's items fill the slots from the first
BAG_ITEMS = 6
GIVE_ITEMS = 2  # what you hand an NPC fills its slots from the first
TRADE_ITEMS = 1  # what the other side offers fills its slots from the first; yours share the give window's EQTypes
LOOT_ITEMS = 3  # a corpse's items fill its slots from the first
HELD_SLOTS = {13, 22}  # the primary hand and the first bag, on the hot bar's slots
LABELS = {
    1: 'Sebik', 12: '60', 13: '45', 14: '38', 15: '41', 16: '52', 17: '4321', 18: '4970', 19: '87', 20: '64',
    28: 'a gnoll pup', 29: '73', 35: '98', 36: '64', 37: '31', 38: '100', 39: '0', 69: '80', 81: '12', 86: '45',
    124: '2210', 125: '3450', 134: 'Complete Healing',
    **{45 + n: name for n, name in enumerate(BUFFS)},
    **{135 + n: name for n, name in enumerate(SONGS)},
    **{60 + n: name for n, name in enumerate(GEMS) if name},
}
GAUGES = {1: 0.87, 2: 0.64, 3: 0.5, 6: 0.73, 7: 0.45, 8: 0.6, 11: 0.98, 12: 0.64, 13: 0.31, 14: 1.0, 16: 0.8,
          17: 0.8, 18: 0.45, 24: 0.5, 25: 0.5, 27: 0.6, 32: 0.25}
GAUGE_TEXT = {11: 'Sebik', 12: 'Warrior', 13: 'Cleric', 14: 'Enchanter', 16: 'Gobaner', 17: 'Kibartik', 18: 'Labn'}
BUTTON_TEXT = {
    'AAP_FirstAbilityButton': 'Sense Heading', 'AAP_SecondAbilityButton': 'Forage', 'AAP_ThirdAbilityButton': 'Hide',
    'AAP_FourthAbilityButton': 'Sneak', 'AAP_FifthAbilityButton': 'Mend', 'AAP_SixthAbilityButton': 'Pick Pockets',
    'ACP_FirstAbilityButton': 'Kick', 'ACP_SecondAbilityButton': 'Dragon Punch', 'ACP_ThirdAbilityButton': 'Flying Kick',
    'ACP_FourthAbilityButton': 'Taunt',
    **{f'ASP_SocialButton{n}': name for n, name in enumerate(
        ['Assist', 'Pull', 'Camp Out', 'Train Pet', 'Mez', 'Sit Down', 'Pull Mob', 'Rez Me', 'Heals', 'Buffs',
         'Loot All', 'Tell Grp'], 1)},
    'HB_Button1': 'Heal', 'HB_Button4': 'Assist', 'HB_Button5': 'Camp', 'HB_Button6': 'Loot',
    'GVW_MyMoney0': '12', 'GVW_MyMoney1': '3', 'GVW_MyMoney2': '0', 'GVW_MyMoney3': '0',
    'TRDW_HisMoney0': '120', 'TRDW_HisMoney1': '5', 'TRDW_HisMoney2': '0', 'TRDW_HisMoney3': '0',
    'TRDW_MyMoney0': '0', 'TRDW_MyMoney1': '0', 'TRDW_MyMoney2': '0', 'TRDW_MyMoney3': '0',
}
# Labels with no EQType whose text the client writes, by ScreenID. The other side of a trade is a placeholder, not a
# character's name.
LABEL_TEXT = {'GVW_NPCName': 'Captain Tillin', 'TRDW_HisName': 'Trader', 'TRDW_MyName': 'Sebik',
              'LW_CorpseName': "a gnoll pup's corpse"}
EDIT_TEXT = {'QTYW_SliderInput': '12', 'CWChatInput': 'Hail, a gnoll pup'}
STML_TEXT = {
    'TextOutput': 'Sebik wants to RESURRECT you. Do you wish this?',
    'CWChatOutput': "You say, 'Hail, a gnoll pup'\nA gnoll pup says, 'Grrr!'\nSebik tells the group, 'incoming'\n"
                    'You have gained experience!',
    'ItemDescription': 'MAGIC ITEM  LORE ITEM\nSlot: PRIMARY SECONDARY\nSkill: 1H Slashing   Atk Delay: 24\n'
                       'DMG: 10  AC: 5\nSTR: +5  STA: +5  HP: +25\nSV FIRE: +5  SV COLD: +5\nWT: 8.0   Size: MEDIUM\n'
                       'Class: WAR PAL RNG SHD BRD ROG\nRace: ALL\nEffect: Lifetap (Combat)',
}
CLASSES = ['Cleric', 'Warrior', 'Enchanter', 'Shadow Knight', 'Druid', 'Bard', 'Necromancer', 'Monk', 'Shaman']
LIST_ROWS = {
    'RAID_PlayerList': [[str(1 + n // 6), 'Sebik' if n == 0 else f'Player {n + 1}', '', CLASSES[n % len(CLASSES)],
                         'Raid Leader' if n == 0 else ('Group Leader' if n % 6 == 0 else '')] for n in range(18)],
    'RAID_NotInGroupPlayerList': [['', f'Player {n + 19}', '', CLASSES[n + 3], ''] for n in range(2)],
}
TITLES = {'ItemDisplayWindow': 'Fine Steel Long Sword', 'ChatWindow': 'Main'}  # names the client writes
SLIDER = (12, 20)  # value, most
ITEM_DECALS = {'IconButton', 'MW_SelectedItem'}  # decals the client fills with an item's icon, not a spell's
HIDDEN = {'OK_Button'}  # what the client hides in the sample state: a Yes/No question shows no OK
BAG = (10, True)  # slots, tradeskill: the game sizes the bag window around them
HEADING = 20  # which way you face, degrees clockwise from north: the game slides the compass's strips to it


def xml_root(data):
    return ET.fromstring(data)


def number(element, tag, default=0):
    text = element.findtext(tag)
    return int(text) if text not in (None, '') else default


def flag(element, tag, default=False):
    text = element.findtext(tag)
    return default if text is None else text == 'true'


def color(element, tag, default=skin.TEXT_RGB):
    found = element.find(tag)
    return default if found is None else tuple(number(found, c) for c in 'RGB')


def place(element, width, height):
    """(x, y, w, h) of a control inside a parent of width × height: from its anchors when it stretches."""
    if flag(element, 'AutoStretch'):
        left = number(element, 'LeftAnchorOffset')
        top = number(element, 'TopAnchorOffset')
        right = number(element, 'RightAnchorOffset')
        bottom = number(element, 'BottomAnchorOffset')
        if not flag(element, 'TopAnchorToTop', True):
            top = height - top
        right = right if flag(element, 'RightAnchorToLeft') else width - right
        bottom = bottom if flag(element, 'BottomAnchorToTop') else height - bottom
        return left, top, right - left, bottom - top
    return (number(element, 'Location/X'), number(element, 'Location/Y'),
            number(element, 'Size/CX'), number(element, 'Size/CY'))


def font(size):
    for path in ARIAL:
        if Path(path).is_file():
            return ImageFont.truetype(path, FONT_PX.get(size, 12))
    return ImageFont.load_default(FONT_PX.get(size, 12))


def button_text_center(size, font_size):
    """Where a button's own text is centered (anchor 'mm'), from the button's top left: its middle, lowered to the
    game's ink like a label's text (see INK_SHIFT)."""
    return size[0] / 2, size[1] / 2 + INK_SHIFT.get(font_size, 0)


def button_text_mask(text, size, font_size):
    """A button's own text as drawn here, as its ink's coverage on an L image the button's size: the builder paints
    Close's name from it (skin.CLOSE_INK), since the game writes nothing on a close box."""
    mask = Image.new('L', size, 0)
    ImageDraw.Draw(mask).text(button_text_center(size, font_size), text, font=font(font_size), anchor='mm', fill=255)
    return mask


def text_mask(text, font_size):
    """A line of text as Preview.text draws it, as its ink's coverage on an L image its line's size: the builder
    paints the quantity window's name from it (skin.QUANTITY_TITLE_INK), since the game would center it on the bar."""
    face = font(font_size)
    mask = Image.new('L', (round(face.getlength(text)), LINE_HEIGHT.get(font_size, 14)), 0)
    ImageDraw.Draw(mask).text((0, INK_SHIFT.get(font_size, 0)), text, font=face, fill=255)
    return mask


def tinted(image, rgb):
    r, g, b, a = image.split()
    channels = [c.point(lambda v, t=t: v * t // 255) for c, t in zip((r, g, b), rgb)]
    return Image.merge('RGBA', (*channels, a))


def tiled(image, width, height):
    out = Image.new('RGBA', (max(width, 0), max(height, 0)), (0, 0, 0, 0))
    if image.width and image.height:
        for y in range(0, height, image.height):
            for x in range(0, width, image.width):
                out.paste(image, (x, y))
    return out


def wrapped(text, face, width):
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split(' '):
            candidate = f'{line} {word}' if line else word
            if line and face.getlength(candidate) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


class Preview:
    """The builder's files, parsed, and the drawing of each window from them."""

    def __init__(self, files, eq_dir=None):
        self.files = files
        root = xml_root(files[skin.ANIMATIONS_FILE])
        self.animations = {e.get('item'): e for e in root.iter('Ui2DAnimation')}
        self.templates = {e.get('item'): e for tag in ('WindowDrawTemplate', 'FrameTemplate', 'SliderDrawTemplate')
                          for e in root.iter(tag)}
        self.textures = {}
        self.fonts = {}
        self.icon_sheets = self.stock_icons(eq_dir)
        self.hidden = set(HIDDEN)

    @staticmethod
    def stock_icons(eq_dir):
        """The stock item and spell icon sheets, (sheet, cell size, cells per row) each, or None."""
        folders = [Path(eq_dir)] if eq_dir else [Path(d) for d in EQ_DIRS if d]
        for folder in folders:
            default = folder / 'uifiles' / 'default'
            items, spells = default / 'dragitem1.tga', default / 'gemicons01.tga'
            if items.is_file() and spells.is_file():
                return {'item': (Image.open(items).convert('RGBA'), 40, 6),
                        'spell': (Image.open(spells).convert('RGBA'), 24, 10)}
        return None

    def font(self, size):
        if size not in self.fonts:
            self.fonts[size] = font(size)
        return self.fonts[size]

    def texture(self, name):
        if name not in self.textures:
            data = self.files.get(name)
            self.textures[name] = Image.open(io.BytesIO(data)).convert('RGBA') if data else None
        return self.textures[name]

    def art(self, name):
        """An animation's first frame, cut from its texture, or None for one TriageUI doesn't define."""
        anim = self.animations.get(name)
        if anim is None:
            return None
        frame = anim.find('Frames')
        texture = self.texture(frame.findtext('Texture'))
        if texture is None:
            return None
        x, y = number(frame, 'Location/X'), number(frame, 'Location/Y')
        w, h = number(frame, 'Size/CX'), number(frame, 'Size/CY')
        return texture.crop((x, y, x + w, y + h))  # past the texture's edge is clear, as the % sign's fill needs

    def icon(self, kind, cell, size):
        if self.icon_sheets is None or cell is None:
            square = Image.new('RGBA', size, PLACEHOLDER_RGBA)
            return square if cell is not None else None
        sheet, side, per_row = self.icon_sheets[kind]
        x, y = cell % per_row * side, cell // per_row * side
        return sheet.crop((x, y, x + side, y + side)).resize(size, Image.BILINEAR)

    def text(self, layer, xy, text, size, rgb, width=None, align='left'):
        face = self.font(size)
        x, y = xy
        if width is not None and align != 'left':
            gap = width - face.getlength(text)
            x += gap if align == 'right' else gap / 2
        ImageDraw.Draw(layer).text((round(x), y + INK_SHIFT.get(size, 0)), text, font=face, fill=(*rgb, 255))

    # The frame

    def frame(self, template, width, height, background=True, border=True):
        """A window frame as the client draws it: the background inside the border, sides repeated, corners."""
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        found = self.templates.get(template)
        if found is None:
            return image, (0, 0, 0, 0)
        pieces = {side.tag: self.art(side.text) for side in found.find('Border') if side.text}
        left = pieces['Left'].width if border and pieces.get('Left') else 0
        right = pieces['Right'].width if border and pieces.get('Right') else 0
        top = pieces['Top'].height if border and pieces.get('Top') else 0
        bottom = pieces['Bottom'].height if border and pieces.get('Bottom') else 0
        fill = self.texture(found.findtext('Background') or '')
        if background and fill is not None:
            image.alpha_composite(tiled(fill, width - left - right, height - top - bottom), (left, top))
        if border:
            for side, x, y, w, h in (('Top', left, 0, width - left - right, top),
                                     ('Bottom', left, height - bottom, width - left - right, bottom),
                                     ('Left', 0, top, left, height - top - bottom),
                                     ('Right', width - right, top, right, height - top - bottom)):
                if pieces.get(side) and w > 0 and h > 0:
                    image.alpha_composite(tiled(pieces[side], w, h), (x, y))
            for side, x, y in (('TopLeft', 0, 0), ('TopRight', width - right, 0),
                               ('BottomLeft', 0, height - bottom), ('BottomRight', width - right, height - bottom)):
                if pieces.get(side):
                    image.alpha_composite(pieces[side], (x, y))
        return image, (left, top, right, bottom)

    def title_bar(self, image, window, template, edges, state):
        """The title bar along the inside's top, its close box, and the window's name; returns its height."""
        found = self.templates.get(template)
        bar = found.find('Titlebar') if found is not None else None
        middle = self.art(bar.findtext('Middle')) if bar is not None else None
        if middle is None:
            return 0
        left, top, right, _ = edges
        inside = image.width - left - right
        ends = {side: self.art(bar.findtext(side)) for side in ('Left', 'Right')}
        image.alpha_composite(tiled(middle, inside, middle.height), (left, top))
        if ends['Left'] is not None:
            image.alpha_composite(ends['Left'], (left, top))
        if ends['Right'] is not None:
            image.alpha_composite(ends['Right'], (left + inside - ends['Right'].width, top))
        if flag(window, 'Style_Closebox'):
            close = self.art(found.findtext(f'CloseBox/{state}') or found.findtext('CloseBox/Normal'))
            if close is not None:  # eqgame.exe: 7 in from the inside's right edge, 1 under its top
                image.alpha_composite(close, (image.width - right - skin.CLOSE_BOX_INSET - close.width,
                                              top + skin.CLOSE_BOX_TOP))
        name = TITLES.get(window.get('item'), window.findtext('Text') or '')
        size = number(window, 'Font', 3)
        # DrawTitleBar: centered across the bar, (bar height - font height) / 2 - 1 down.
        self.text(image, (left, top + (middle.height - LINE_HEIGHT.get(size, 14)) // 2 - 1), name, size, TITLE_RGB,
                  width=inside, align='center')
        return middle.height

    # The pieces

    def pieces(self, layer, names, defined, origin, area, state, page):
        drawn = set()
        for name in names:
            element = defined[name]
            x, y, w, h = place(element, *area)
            if w <= 0 or h <= 0 or element.findtext('ScreenID') in self.hidden:
                continue  # hidden: the client finds it but nothing shows
            if element.findtext('ScreenID') in skin.COMPASS_STRIPS:
                x = self.strip_x(element.findtext('ScreenID'))
            if element.tag == 'Button':
                if (x, y, w, h) in drawn:
                    continue  # a pair sharing a spot (Invite and Follow): the client shows one
                drawn.add((x, y, w, h))
            draw = getattr(self, f'draw_{element.tag.lower()}', None)
            if draw is not None:
                draw(layer, element, (origin[0] + x, origin[1] + y), (w, h), defined, state, page)

    def draw_screen(self, layer, element, at, size, defined, state, page):
        """A child window: its template's look unless transparent, and what it holds, clipped to it."""
        clip = Image.new('RGBA', size, (0, 0, 0, 0))
        template = element.findtext('DrawTemplate')
        if template and not flag(element, 'Style_Transparent'):
            clip, _ = self.frame(template, *size, border=flag(element, 'Style_Border'))
        self.pieces(clip, [p.text for p in element.findall('Pieces')], defined, (0, 0), size, state, page)
        layer.alpha_composite(clip, at)

    @staticmethod
    def strip_x(screen_id):
        """Where the game slides a compass strip for the sample heading, across the inside: the heading's mark on the
        pointer, as the stock art lines them up (see COMPASS_FILE in build_skin.py), and the other copy on whichever
        side covers the rest."""
        mark = int(skin.COMPASS_NORTH_X + HEADING * skin.COMPASS_STRIP_WIDTH / 360) % skin.COMPASS_STRIP_WIDTH
        first = skin.COMPASS_POINTER_X - mark
        if screen_id == skin.COMPASS_STRIPS[0]:
            return first
        return first - skin.COMPASS_STRIP_WIDTH if first > 0 else first + skin.COMPASS_STRIP_WIDTH

    def draw_staticanimation(self, layer, element, at, size, *_):
        art = self.art(element.findtext('Animation'))
        if art is not None:
            x, y = at  # a compass strip starts left of the inside: only what's inside is drawn
            layer.alpha_composite(art if art.size == size else art.resize(size), (max(x, 0), max(y, 0)),
                                  (max(-x, 0), max(-y, 0)))

    def draw_label(self, layer, element, at, size, *_):
        eq_type = element.findtext('EQType')
        text = LABELS.get(int(eq_type), '') if eq_type else (
            LABEL_TEXT.get(element.findtext('ScreenID') or '') or element.findtext('Text') or '')
        clip = Image.new('RGBA', size, (0, 0, 0, 0))
        align = 'right' if flag(element, 'AlignRight') else 'center' if flag(element, 'AlignCenter') else 'left'
        self.text(clip, (0, 0), text, number(element, 'Font', 3), color(element, 'TextColor'), size[0], align)
        layer.alpha_composite(clip, at)

    def draw_gauge(self, layer, element, at, size, *_):
        eq_type = number(element, 'EQType')
        clip = Image.new('RGBA', size, (0, 0, 0, 0))
        offset = (number(element, 'GaugeOffsetX'), number(element, 'GaugeOffsetY', 16))
        template = element.find('GaugeDrawTemplate')
        track = self.art(template.findtext('Background') or '')
        if track is not None:
            clip.alpha_composite(track, offset)
        fill = self.art(template.findtext('Fill') or '')
        value = GAUGES.get(eq_type, 0)
        if fill is not None and round(fill.width * value):
            fill = fill.crop((0, 0, round(fill.width * value), fill.height))
            clip.alpha_composite(tinted(fill, color(element, 'FillTint', (255, 255, 255))), offset)
        text = GAUGE_TEXT.get(eq_type, '')
        if text:  # its own text, where TextOffset puts it (far outside hides it)
            self.text(clip, (number(element, 'TextOffsetX'), number(element, 'TextOffsetY')), text,
                      number(element, 'Font', 3), color(element, 'TextColor'))
        layer.alpha_composite(clip, at)

    def draw_button(self, layer, element, at, size, defined, state, _page):
        screen_id = element.findtext('ScreenID') or ''
        effect = self.effect(screen_id, defined)
        templates = element.find('ButtonDrawTemplate')
        name = 'RedIconBackground' if effect is not None and screen_id in HARMFUL else (
            templates.findtext(state) or templates.findtext('Normal'))
        art = self.art(name or '')
        if art is not None:
            layer.alpha_composite(art.crop((0, 0, *size)), at)
        if templates.find('NormalDecal') is not None:
            kind = 'item' if screen_id in ITEM_DECALS else 'spell'
            cell = 7 + 9 * effect if effect is not None else 14 if screen_id in ITEM_DECALS else None
            icon = self.icon(kind, cell, (number(element, 'DecalSize/CX'), number(element, 'DecalSize/CY')))
            if icon is not None:
                layer.alpha_composite(icon, (at[0] + number(element, 'DecalOffset/X'),
                                             at[1] + number(element, 'DecalOffset/Y')))
        text = element.findtext('Text') or BUTTON_TEXT.get(screen_id, '')
        if text and element.find('Font') is not None:
            size_n = number(element, 'Font', 3)
            x, y = button_text_center(size, size_n)
            ImageDraw.Draw(layer).text((at[0] + x, at[1] + y), text, font=self.font(size_n), anchor='mm',
                                       fill=(*color(element, 'TextColor'), 255))

    @staticmethod
    def effect(screen_id, defined):
        """An effect slot's number when its name label has a sample (an effect is on it), else None."""
        if not (screen_id.startswith('Buff') and screen_id[4:].isdigit()):
            return None
        labels = [e for e in defined.values() if e.tag == 'Label' and e.findtext('ScreenID') == f'{screen_id}Label']
        eq_type = labels[0].findtext('EQType') if labels else None
        return int(screen_id[4:]) if eq_type and LABELS.get(int(eq_type)) else None

    @staticmethod
    def item_cell(eq_type, screen_id):
        """Which item icon a slot shows, or None for an empty one."""
        if screen_id in HOT_ITEMS:
            return HOT_ITEMS[screen_id]
        merchant = skin.MERCHANT_SLOT_TYPE <= eq_type < skin.MERCHANT_SLOT_TYPE + MERCHANT_ITEMS
        bag = skin.BAG_SLOT_TYPE <= eq_type < skin.BAG_SLOT_TYPE + BAG_ITEMS
        given = skin.GIVE_SLOT_TYPE <= eq_type < skin.GIVE_SLOT_TYPE + GIVE_ITEMS
        theirs = skin.TRADE_SLOT_TYPE + skin.TRADE_SLOTS
        offered = theirs <= eq_type < theirs + TRADE_ITEMS
        looted = skin.LOOT_SLOT_TYPE <= eq_type < skin.LOOT_SLOT_TYPE + LOOT_ITEMS
        held = merchant or bag or given or offered or looted or eq_type in HELD_SLOTS
        return (eq_type * 7 + 3) % 36 if held else None

    def draw_invslot(self, layer, element, at, size, *_):
        screen_id = element.findtext('ScreenID') or ''
        eq_type = number(element, 'EQType', -1)
        if eq_type < 0 and screen_id not in HOT_ITEMS:
            return  # a hot button's item spot, shown only while it holds an item
        art = self.art(element.findtext('Background') or '')
        if art is not None:
            layer.alpha_composite(art.crop((0, 0, *size)), at)
        cell = self.item_cell(eq_type, screen_id)
        if cell is not None:
            layer.alpha_composite(self.icon('item', cell, size), at)

    def draw_spellgem(self, layer, element, at, size, *_):
        screen_id = element.findtext('ScreenID') or ''
        if screen_id.startswith('CSPW_Spell'):
            n = int(screen_id[len('CSPW_Spell'):])
            cell = GEM_ICONS[n] if n < len(GEM_ICONS) else None
        elif screen_id in HOT_SPELLS:
            cell = HOT_SPELLS[screen_id]
        else:
            return  # a hot button's spell spot, shown only while it holds a spell
        art = self.art(element.findtext('SpellGemDrawTemplate/Holder') or '')
        if art is not None:
            layer.alpha_composite(art.crop((0, 0, *size)), at)
        icon = self.icon('spell', cell, (24, 24))
        if icon is not None:
            layer.alpha_composite(icon, (at[0] + number(element, 'SpellIconOffsetX'),
                                         at[1] + number(element, 'SpellIconOffsetY')))

    def draw_editbox(self, layer, element, at, size, *_):
        size_n = number(element, 'Font', 3)
        clip = Image.new('RGBA', size, (0, 0, 0, 0))
        self.text(clip, (0, (size[1] - LINE_HEIGHT.get(size_n, 14)) // 2),
                  EDIT_TEXT.get(element.findtext('ScreenID') or '', ''), size_n, color(element, 'TextColor'))
        layer.alpha_composite(clip, at)

    def draw_stmlbox(self, layer, element, at, size, *_):
        size_n = number(element, 'Font', 3)
        scroll = flag(element, 'Style_VScroll')
        width = size[0] - (skin.SCROLL_WIDTH if scroll else 0)
        lines = wrapped(STML_TEXT.get(element.findtext('ScreenID') or '', ''), self.font(size_n), width)
        clip = Image.new('RGBA', size, (0, 0, 0, 0))
        line = LINE_HEIGHT.get(size_n, 14)
        for n, text in enumerate(lines):
            self.text(clip, (0, n * line), text, size_n, STML_RGB)
        if scroll:
            self.scrollbar(clip, element.findtext('DrawTemplate'), len(lines) * line)
        layer.alpha_composite(clip, at)

    def scrollbar(self, clip, template, content_height):
        """The vertical scrollbar along clip's right edge: its arrows, and a thumb when the content overflows."""
        found = self.templates.get(template or '')
        bar = found.find('VSBTemplate') if found is not None else None
        if bar is None:
            return
        up, down = self.art(bar.findtext('UpButton/Normal')), self.art(bar.findtext('DownButton/Normal'))
        if up is None or down is None:
            return
        x = clip.width - skin.SCROLL_WIDTH
        clip.alpha_composite(up, (x, 0))
        clip.alpha_composite(down, (x, clip.height - down.height))
        track = clip.height - up.height - down.height
        if content_height > clip.height and track > 0:
            top, middle, bottom = (self.art(bar.findtext(f'Thumb/{p}')) for p in ('Top', 'Middle', 'Bottom'))
            if None in (top, middle, bottom):
                return
            length = max(top.height + bottom.height + 1, track * clip.height // content_height)
            tx = x + (skin.SCROLL_WIDTH - top.width) // 2
            clip.alpha_composite(top, (tx, up.height))
            clip.alpha_composite(tiled(middle, middle.width, length - top.height - bottom.height),
                                 (tx, up.height + top.height))
            clip.alpha_composite(bottom, (tx, up.height + length - bottom.height))

    def draw_listbox(self, layer, element, at, size, *_):
        size_n = number(element, 'Font', 3)
        rgb = color(element, 'TextColor')
        clip = Image.new('RGBA', size, (0, 0, 0, 0))
        columns = [(c.findtext('Heading') or '', number(c, 'Width'), c.findtext('Header')) for c in
                   element.findall('Columns')]
        header = 0
        x = 0
        for heading, width, frame in columns:
            strip = self.templates.get(frame or '')
            wash = self.art(strip.findtext('Middle')) if strip is not None else None
            if wash is not None and width:
                clip.alpha_composite(tiled(wash, width, wash.height), (x, 0))
                header = max(header, wash.height)
            if width:
                y = (wash.height - LINE_HEIGHT.get(size_n, 14)) // 2 if wash is not None else 0
                self.text(clip, (x, y), heading, size_n, rgb)
            x += width
        line = LINE_HEIGHT.get(size_n, 14)
        rows = LIST_ROWS.get(element.findtext('ScreenID') or '', [])
        for r, cells in enumerate(rows):
            x = 0
            for (_, width, _), text in zip(columns, cells):
                if width:
                    cell = Image.new('RGBA', (width, line), (0, 0, 0, 0))
                    self.text(cell, (0, 0), text, size_n, rgb)
                    clip.alpha_composite(cell, (x, header + r * line))
                x += width
        if flag(element, 'Style_VScroll'):
            self.scrollbar(clip, element.findtext('DrawTemplate'), header + len(rows) * line)
        layer.alpha_composite(clip, at)

    def draw_slider(self, layer, element, at, size, _defined, state, _page):
        """eqgame.exe's slider: caps at the ends, the background between them, the thumb's left edge at the left
        cap + (width - caps) × value / most, its top the background's."""
        art = self.templates.get(element.findtext('SliderArt') or '')
        if art is None:
            return
        left, right, track = (self.art(art.findtext(p)) for p in ('EndCapLeft', 'EndCapRight', 'Background'))
        if None in (left, right, track):
            return
        span = size[0] - left.width - right.width
        top = (size[1] - track.height) // 2
        layer.alpha_composite(tiled(track, span, track.height), (at[0] + left.width, at[1] + top))
        if right.width:
            layer.alpha_composite(right, (at[0] + size[0] - right.width, at[1] + top))
        knob = self.art(art.findtext(f'Thumb/{state}') or art.findtext('Thumb/Normal'))
        value, most = SLIDER
        x = left.width + span * value // most
        if knob is not None:
            layer.alpha_composite(knob.crop((0, 0, min(knob.width, size[0] - x), knob.height)),
                                  (at[0] + x, at[1] + top))

    def draw_tabbox(self, layer, element, at, size, defined, state, page):
        """The tabs as the client lays them out (see TAB_BORDER in build_skin.py), then the open page."""
        pages = [defined[p.text] for p in element.findall('Pages')]
        if not pages:
            return
        page = min(page, len(pages) - 1)
        shares = size[0] - 2 * skin.TAB_CORNER
        for i, tab in enumerate(pages):
            art = self.art(tab.findtext('TabIconActive' if i == page else 'TabIcon') or '')
            if art is not None:
                layer.alpha_composite(art, (at[0] + skin.TAB_OFFSET + shares * i // len(pages) + skin.TAB_ICON_INSET,
                                            at[1] + skin.TAB_TOP + (0 if i == page else skin.TAB_SHIFT)))
        area = (size[0] - 2 * skin.LEFT, size[1] - skin.PAGE_TOP)
        self.pieces(layer, [p.text for p in pages[page].findall('Pieces')], defined,
                    (at[0] + skin.LEFT, at[1] + skin.PAGE_TOP), area, state, page)

    # A window

    def window(self, name):
        root = xml_root(self.files[name])
        return root, [e for e in root if e.tag == 'Screen'][-1]

    def pages(self, name):
        """How many looks the window has: one per page of its TabBox, else one."""
        root, _ = self.window(name)
        return max([len(tab.findall('Pages')) for tab in root.iter('TabBox')] + [1])

    @staticmethod
    def bag_size(window, defined):
        """The bag window's size as the game makes it (eqgame.exe's SetContainer, see bag_layout() in the tests): a
        box around the label, the icon and the bag's slots, then Combine (in a tradeskill container) and Done each
        BAG_BUTTON_GAP under it, the window the box plus BAG_EXTRA_WIDTH across and BAG_EXTRA_HEIGHT down."""
        controls = {defined[p.text].findtext('ScreenID'): defined[p.text] for p in window.findall('Pieces')}
        slots, tradeskill = BAG
        edges = []
        for screen_id in ['Container_Label', 'Container_Icon', *(f'ContainerSlot{n}' for n in range(1, slots + 1))]:
            x, y, w, h = place(controls[screen_id], 0, 0)
            edges.append((x, y, x + w, y + h))
        left, top = min(e[0] for e in edges), min(e[1] for e in edges)
        right, bottom = max(e[2] for e in edges), max(e[3] for e in edges)
        for screen_id in (['Container_Combine'] if tradeskill else []) + ['DoneButton']:
            bottom += skin.BAG_BUTTON_GAP + number(controls[screen_id], 'Size/CY')
        return right - left + skin.BAG_EXTRA_WIDTH, bottom - top + skin.BAG_EXTRA_HEIGHT

    def render(self, name, state='Normal'):
        """The window drawn once per page, each image the window's own size."""
        root, window = self.window(name)
        defined = {e.get('item'): e for e in root}
        width, height = number(window, 'Size/CX'), number(window, 'Size/CY')
        if window.get('item') == 'ContainerWindow':
            width, height = self.bag_size(window, defined)
            slots, tradeskill = BAG
            self.hidden |= {f'ContainerSlot{n}' for n in range(slots + 1, skin.BAG_SLOTS + 1)}
            self.hidden |= set() if tradeskill else {'Container_Combine'}
        template = window.findtext('DrawTemplate') or skin.FRAME_TEMPLATE
        images = []
        for page in range(self.pages(name)):
            image, edges = self.frame(template, width, height, border=flag(window, 'Style_Border', True))
            bar = self.title_bar(image, window, template, edges, state) if flag(window, 'Style_Titlebar') else 0
            left, top, right, bottom = edges
            area = (width - left - right, height - top - bottom - bar)
            # The client draws nothing outside the inside: the pieces go onto it, cut out with its panel, and back.
            inside = image.crop((left, top + bar, left + area[0], top + bar + area[1]))
            self.pieces(inside, [p.text for p in window.findall('Pieces')], defined, (0, 0), area, state, page)
            image.paste(inside, (left, top + bar))
            images.append(image)
        return images

    def sheet(self, name, state='Normal', scale=3):
        """Every page of the window on a backdrop, stacked, scaled up without smoothing."""
        images = self.render(name, state)
        width = max(i.width for i in images) + 2 * MARGIN
        height = sum(i.height for i in images) + MARGIN * (len(images) + 1)
        sheet = Image.new('RGBA', (width, height), BACKDROP)
        y = MARGIN
        for image in images:
            sheet.alpha_composite(image, (MARGIN, y))
            y += image.height + MARGIN
        return sheet.resize((width * scale, height * scale), Image.NEAREST)


def skin_files(cache_dir):
    """The builder's files, made in memory, or kept from the last run while build_skin.py is unchanged."""
    key = hashlib.sha256((REPO / 'build_skin.py').read_bytes()).hexdigest()
    cache = Path(cache_dir) / CACHE_FILE
    if cache.is_file():
        try:
            saved_key, files = pickle.loads(cache.read_bytes())
            if saved_key == key:
                return files
        except (pickle.UnpicklingError, EOFError, ValueError):
            pass
    files = skin.skin_files(BASE_ANIMATIONS)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps((key, files)))
    return files


def chosen(words):
    """The window files whose names contain any of words (every window without words)."""
    names = list(skin.WINDOW_FILES)
    if not words:
        return names
    picked = [n for n in names if any(w.lower() in n.lower() for w in words)]
    if not picked:
        raise SystemExit(f'No window file matches {", ".join(words)}. Files: {", ".join(names)}')
    return picked


def save(preview, names, out, state='Normal', scale=3):
    """Writes out/<file>.png for each window file; returns the paths."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in names:
        path = out / f'{Path(name).stem}.png'
        preview.sheet(name, state, scale).save(path)
        paths.append(path)
    return paths


def main(argv=None):
    parser = argparse.ArgumentParser(description='Draws TriageUI windows as PNGs for a look before going in game.')
    parser.add_argument('windows', nargs='*', help='words from the window files\' names (default: every window)')
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT, help='where the PNGs go (default: build/preview)')
    parser.add_argument('--scale', type=int, default=3, help='how many times bigger (default: 3)')
    parser.add_argument('--state', default='Normal', choices=['Normal', 'Flyby', 'Pressed', 'Disabled'],
                        help='the state every button is drawn in')
    parser.add_argument('--eq', type=Path, help='an EverQuest folder, for the stock item and spell icons')
    args = parser.parse_args(argv)
    names = chosen(args.windows)
    preview = Preview(skin_files(args.out), args.eq)
    for path in save(preview, names, args.out, args.state, args.scale):
        print(path)


if __name__ == '__main__':
    main()
