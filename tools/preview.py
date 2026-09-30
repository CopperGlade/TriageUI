"""Draws TriageUI's windows as PNGs, from the XML and textures the builder makes, with sample names and values, for a
look before going in game.

    python tools/preview.py                every window
    python tools/preview.py quantity item  the windows whose file name contains one of the words
    python tools/preview.py icons          the spell icons (spell_icons.png), --compare duxaUI beside that skin's

It writes build/preview/<file>.png (--out to change), the window on a backdrop, 3x (--scale). --state draws every
button in another state (Flyby, Pressed, Disabled). Spell icons are TriageUI's own; item icons come from the stock
skin when an EverQuest folder is found (EQ_DIR, C:\\QUARM or the Mac mount), grey squares otherwise.

It draws what the XML says the way the client does: the frame, title bar and close box from the window's template,
then each piece in order, clipped to the window's inside. A child Screen clips what it holds, anchored controls take
their place from their anchors, a TabBox is drawn once per page, stacked, and a Combobox closed, showing its choice. The bag window is sized as the game
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
ICON_SHEET_FILE = 'spell_icons.png'
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
HARMFUL = {'Buff3', 'SBW_Spell5', 'SBW_Spell12'}  # the client paints these slots RedIconBackground (Root, Stun)
SONGS = ["Selo's Accelerando", 'Chant of Battle', "Cassindra's Chorus of Clarity"]
GEMS = ['Complete Healing', 'Divine Aura', 'Superior Healing', 'Symbol of Marzin', 'Resolution', None, 'Root', 'Gate']
# Each sample spell's icon: its cell in A_SpellIcons and A_SpellGems (spells_en.txt's field 131).
SPELL_ICONS = {
    'Aegolism': 132, 'Spirit of Wolf': 4, 'Clarity': 21, 'Tashanian': 72, 'Regrowth of Dar Khura': 118,
    'Blessing of Temperance': 132, 'Resist Magic': 69, 'Talisman of Tnarg': 130, "Selo's Accelerando": 4,
    'Chant of Battle': 143, "Cassindra's Chorus of Clarity": 24, 'Complete Healing': 99, 'Divine Aura': 46,
    'Superior Healing': 99, 'Symbol of Marzin': 150, 'Resolution': 132, 'Root': 117, 'Gate': 31,
    'Transons Phantasmal Protection': 152, 'Yaulp IV': 6, 'Word of Healing': 99, 'Spirit Armor': 151,
    'Heroic Bond': 132, 'Stun': 25,
}
GEM_ICONS = [SPELL_ICONS.get(name) for name in GEMS]
# A spread of the spell book: (name, icon cell) in reading order on the left page, then the right, the last slots
# empty. One name is the longest any class can scribe, to show it fits on its lines.
BOOK = [(name, SPELL_ICONS[name]) for name in (
    'Complete Healing', 'Superior Healing', 'Divine Aura', 'Symbol of Marzin', 'Resolution', 'Root', 'Gate',
    'Transons Phantasmal Protection', 'Yaulp IV', 'Word of Healing', 'Spirit Armor', 'Heroic Bond', 'Stun')]
BOOK_PAGES = ('12', '13')
# The hot bar's item and spell spots show only on a hot button holding one: one of each here, the rest macros.
HOT_ITEMS = {'HB_InvSlot3': 20}
HOT_SPELLS = {'HB_SpellGem2': SPELL_ICONS['Spirit of Wolf']}
MERCHANT_ITEMS = 23  # a merchant's items fill the slots from the first
BAG_ITEMS = 6
GIVE_ITEMS = 2  # what you hand an NPC fills its slots from the first
TRADE_ITEMS = 1  # what the other side offers fills its slots from the first; yours share the give window's EQTypes
LOOT_ITEMS = 3  # a corpse's items fill its slots from the first
BANK_ITEMS = 7  # the first bank slots, down the first column and into the second
SHARED_ITEMS = 2
# The primary hand and the first bag, on the hot bar's slots; the head and chest too, in the inventory.
HELD_SLOTS = {2, 13, 17, 22}
# What the inspected player wears, by worn slot (the slot's EQType less the inspect window's first): the head, the chest
# and both hands.
INSPECTED_SLOTS = {2, 13, 14, 17}
LABELS = {
    1: 'Sebik', 2: '60', 3: 'Shadow Knight', 4: 'Mithaniel Marr', 5: '185', 6: '210', 7: '110', 8: '95', 9: '80',
    10: '75', 11: '60', 22: '1234', 23: '987', 24: '85', 25: '150', 26: '45', 27: '12',
    12: '60', 13: '45', 14: '38', 15: '41', 16: '52', 17: '4321', 18: '4970', 19: '87', 20: '64',
    28: 'a gnoll pup', 29: '73', 35: '98', 36: '64', 37: '31', 38: '100', 39: '0', 69: '80', 81: '12', 86: '45',
    124: '2210', 125: '3450', 134: 'Complete Healing',
    **{45 + n: name for n, name in enumerate(BUFFS)},
    **{135 + n: name for n, name in enumerate(SONGS)},
    **{60 + n: name for n, name in enumerate(GEMS) if name},
}
GAUGES = {1: 0.87, 2: 0.64, 3: 0.5, 4: 0.45, 5: 0.12, 6: 0.73, 7: 0.45, 8: 0.6, 9: 0.4, 11: 0.98, 12: 0.64, 13: 0.31, 14: 1.0, 16: 0.8,
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
    'BW_Money0': '1234567', 'BW_Money1': '27', 'BW_Money2': '4', 'BW_Money3': '9',
    'IW_Money0': '123456', 'IW_Money1': '12', 'IW_Money2': '3', 'IW_Money3': '4',
}
# Labels with no EQType whose text the client writes, by ScreenID. The other side of a trade is a placeholder, not a
# character's name.
LABEL_TEXT = {'GVW_NPCName': 'Captain Tillin', 'TRDW_HisName': 'Trader', 'TRDW_MyName': 'Sebik',
              'LW_CorpseName': "a gnoll pup's corpse", 'BW_BankerName': 'Banker Denston',
              **{f'SBW_SpellName{n}': name for n, (name, _) in enumerate(BOOK)},
              'SBW_LeftPageNum': BOOK_PAGES[0], 'SBW_RightPageNum': BOOK_PAGES[1],
              # The AA window's: how much XP goes to AA, your points available and spent, and the selected ability's
              # reuse timer.
              'ExpCount': '100%', 'CurrentCount': '12', 'TotalCount': '145', 'Timer': '00:42:10'}
EDIT_TEXT = {'QTYW_SliderInput': '12', 'CWChatInput': 'Hail, a gnoll pup', 'NameInput': 'Player 10',
             'INSW_Edit': 'Looking for a group in Lower Guk. Tells welcome, spells for sale.'}
STML_TEXT = {
    'TextOutput': 'Sebik wants to RESURRECT you. Do you wish this?',
    'CWChatOutput': "You say, 'Hail, a gnoll pup'\nA gnoll pup says, 'Grrr!'\nSebik tells the group, 'incoming'\n"
                    'You have gained experience!',
    'ItemDescription': 'MAGIC ITEM  LORE ITEM\nSlot: PRIMARY SECONDARY\nSkill: 1H Slashing   Atk Delay: 24\n'
                       'DMG: 10  AC: 5\nSTR: +5  STA: +5  HP: +25\nSV FIRE: +5  SV COLD: +5\nWT: 8.0   Size: MEDIUM\n'
                       'Class: WAR PAL RNG SHD BRD ROG\nRace: ALL\nEffect: Lifetap (Combat)',
    # The AA window's selected ability, as the client writes it (eqstr_en.txt 13810 and 3109).
    'Description': 'This ability turns the next group buff that you cast into a beneficial area effect spell, hitting '
                   "everyone within its radius, at the cost of doubling the spell's mana usage.\n"
                   'Type: Activated, Refresh Time: 1:30:00',
}
CLASSES = ['Cleric', 'Warrior', 'Enchanter', 'Shadow Knight', 'Druid', 'Bard', 'Necromancer', 'Monk', 'Shaman']
LIST_ROWS = {
    'RAID_PlayerList': [[str(1 + n // 6), 'Sebik' if n == 0 else f'Player {n + 1}', '', CLASSES[n % len(CLASSES)],
                         'Raid Leader' if n == 0 else ('Group Leader' if n % 6 == 0 else '')] for n in range(18)],
    'RAID_NotInGroupPlayerList': [['', f'Player {n + 19}', '', CLASSES[n + 3], ''] for n in range(2)],
    # The friends window's lists, fewer than they show, as the client lists the names you added.
    'FriendsList': [[f'Player {n}'] for n in range(2, 10)],
    'IgnoreList': [['Player 21']],
    # A bard's skills in the client's order, each with its rank (the words in eqstr_en.txt) and value.
    'SkillList': [[name, rank, str(value)] for name, rank, value in (
        ('1H Blunt', 'Very Good', 182), ('1H Slashing', 'Very Good', 175), ('Archery', 'Below Avg', 45),
        ('Bind Wound', 'Good', 150), ('Brass Instruments', 'Excellent', 190), ('Defense', 'Excellent', 200),
        ('Dodge', 'Above Avg', 125), ('Dual Wield', 'Very Good', 180), ('Hand to Hand', 'Average', 100),
        ('Offense', 'Master', 210), ('Parry', 'Above Avg', 130), ('Pick Lock', 'Average', 95),
        ('Piercing', 'Very Good', 175), ('Riposte', 'Good', 145), ('Safe Fall', 'Average', 80),
        ('Sense Heading', 'Above Avg', 120), ('Singing', 'Excellent', 200), ('Sneak', 'Average', 85),
        ('Stringed Instruments', 'Excellent', 200), ('Swimming', 'Good', 150), ('Throwing', 'Bad', 30),
        ('Tracking', 'Above Avg', 110), ('Wind Instruments', 'Excellent', 195), ('Fishing', 'Feeble', 20),
        ('Baking', 'Bad', 32), ('Tailoring', 'Feeble', 15), ('Blacksmithing', 'Awful', 5), ('Fletching', 'Awful', 3),
        ('Brewing', 'Feeble', 18), ('Alcohol Tolerance', 'Below Avg', 55), ('Begging', 'Awful', 10),
        ('Jewelry Making', 'Awful', 4), ('Pottery', 'Awful', 2), ('Percussion Instruments', 'Excellent', 195))],
}
# What a tracker sees in range, each with its con (an index into the tracking filters, red first), more than the list
# shows so it scrolls.
TRACKED = [
    ('a gnoll pup', 5), ('a large rat', 5), ('a fire beetle', 4), ('a decaying skeleton', 5), ('a moss snake', 5),
    ('a gnoll', 3), ('a black wolf', 3), ('a grizzly bear', 2), ('Sebik', 2), ('a young kodiak', 4),
    ('a gnoll scout', 3), ('a mountain lion', 1), ('Fippy Darkpaw', 3), ('a Sabertooth gnoll guardian', 0),
    ('a giant bat', 4), ('a gnoll watcher', 3), ('an orc pawn', 4), ('a zombie', 4), ('a skeleton', 5),
    ('a spiderling', 5), ('a will-o-wisp', 1), ('a bat', 5), ('a garter snake', 5), ('a wolf', 4), ('a rat', 5),
    ('a bloodgill goblin', 0), ('a timber wolf', 4), ('a brown bear', 3), ('a Sabertooth gnoll', 2),
    ('a highpass guard', 0),
]
LIST_ROWS['TRW_TrackingList'] = [[name] for name, _ in TRACKED]
# Each row's color, where the client colors the rows itself: a tracked name's is its con's.
LIST_RGB = {'TRW_TrackingList': [skin.TRACK_FILTERS[con][3] for _, con in TRACKED]}
# A cleric's alternate abilities on each AA tab, as the client lists them (eqstr_en.txt's names): (name, rank, most,
# the next rank's cost). The General tab has all of its own, the others a few; the widest name any tab lists (Spell
# Casting Reinforcement Mastery) is among the PoP abilities.
AA_ABILITIES = {
    'List1': [(f'Innate {stat}', rank, 5, min(rank + 1, 5)) for stat, rank in (
        ('Strength', 2), ('Stamina', 0), ('Agility', 5), ('Dexterity', 1), ('Intelligence', 0), ('Wisdom', 3),
        ('Charisma', 0), ('Fire Protection', 0), ('Cold Protection', 0), ('Magic Protection', 2),
        ('Poison Protection', 0), ('Disease Protection', 0))] + [
        ('Innate Run Speed', 1, 3, 1), ('Innate Regeneration', 0, 3, 1), ('Innate Metabolism', 0, 3, 1),
        ('Innate Lung Capacity', 0, 3, 1), ('First Aid', 0, 3, 1)],
    'List2': [('Healing Adept', 3, 3, 3), ('Healing Gift', 1, 3, 3), ('Spell Casting Mastery', 0, 3, 2),
              ('Mental Clarity', 2, 3, 3), ('Channeling Focus', 0, 3, 2), ('Mass Group Buff', 0, 1, 9)],
    'List3': [('Divine Resurrection', 0, 1, 5), ('Purify Soul', 0, 1, 5), ('Turn Undead', 1, 5, 2),
              ('Celestial Regeneration', 0, 1, 5), ('Bestow Divine Aura', 0, 1, 5)],
    'List4': [('Advanced Innate Strength', 0, 5, 1), ('Planar Power', 1, 5, 2), ('Planar Durability', 0, 3, 1),
              ('Innate Enlightenment', 0, 5, 1), ('Spell Casting Reinforcement Mastery', 0, 1, 8)],
    'List5': [('Divine Arbitration', 0, 3, 3), ('Hastened Divinity', 0, 3, 2), ('Advanced Healing Adept', 0, 3, 3)],
}
LIST_ROWS.update({list_id: [[name, f'{rank}/{most}', str(cost)] for name, rank, most, cost in abilities]
                  for list_id, abilities in AA_ABILITIES.items()})
COMBO_TEXT = {'TRW_TrackSortCombobox': 'Distance', 'TRW_TrackPlayersCombobox': 'On'}  # the choice each shows
COMBO_TEXT_INSET = skin.FIELD_PADDING  # a guess, like the chat input's text: the client's own is unknown
TITLES = {'ItemDisplayWindow': 'Fine Steel Long Sword', 'ChatWindow': 'Main', 'InspectWnd': 'Sebik'}  # the client's
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
        self.templates = {e.get('item'): e for tag in ('WindowDrawTemplate', 'FrameTemplate', 'SliderDrawTemplate',
                                                       'ButtonDrawTemplate')
                          for e in root.iter(tag) if e.get('item')}
        self.textures = {}
        self.fonts = {}
        self.icon_sheets = self.stock_icons(eq_dir)
        self.hidden = set(HIDDEN)

    @staticmethod
    def stock_icons(eq_dir):
        """The stock item icon sheet, {'item': (sheet, cell size, cells per row)}, or None."""
        folders = [Path(eq_dir)] if eq_dir else [Path(d) for d in EQ_DIRS if d]
        for folder in folders:
            items = folder / 'uifiles' / 'default' / 'dragitem1.tga'
            if items.is_file():
                return {'item': (Image.open(items).convert('RGBA'), 40, 6)}
        return None

    def grid_cell(self, name, cell):
        """Cell cell of the grid animation name, as the client finds it: left to right and down each frame's texture,
        running on from one frame to the next. None past the last."""
        anim = self.animations.get(name)
        width, height = number(anim, 'CellWidth'), number(anim, 'CellHeight')
        for frame in anim.findall('Frames'):
            across = number(frame, 'Size/CX') // width
            count = across * (number(frame, 'Size/CY') // height)
            if cell < count:
                x = number(frame, 'Location/X') + cell % across * width
                y = number(frame, 'Location/Y') + cell // across * height
                return self.texture(frame.findtext('Texture')).crop((x, y, x + width, y + height))
            cell -= count
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
        """An item's icon ('item', from the stock sheet), or a spell's from the grid animation kind names, at size."""
        if cell is None:
            return None
        if kind != 'item':
            return self.grid_cell(kind, cell).resize(size, Image.BILINEAR)
        if self.icon_sheets is None:
            return Image.new('RGBA', size, PLACEHOLDER_RGBA)
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

    def draw_statictext(self, layer, element, at, size, *rest):
        """A label's one line (no EQType, so its text is by ScreenID: the spellbook's names and page numbers), or with
        NoWrap false the text wrapped at the box's width from its top, each line aligned on its own."""
        if flag(element, 'NoWrap', True):
            return self.draw_label(layer, element, at, size, *rest)
        size_n = number(element, 'Font', 3)
        text = LABEL_TEXT.get(element.findtext('ScreenID') or '') or element.findtext('Text') or ''
        align = 'right' if flag(element, 'AlignRight') else 'center' if flag(element, 'AlignCenter') else 'left'
        clip = Image.new('RGBA', size, (0, 0, 0, 0))
        for n, line in enumerate(wrapped(text, self.font(size_n), size[0])):
            self.text(clip, (0, n * LINE_HEIGHT.get(size_n, 14)), line, size_n, color(element, 'TextColor'), size[0],
                      align)
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
        spell = effect is not None or self.book_cell(screen_id) is not None
        name = 'RedIconBackground' if spell and screen_id in HARMFUL else (
            templates.findtext(state) or templates.findtext('Normal'))
        art = self.art(name or '')
        if art is not None and all(size):
            if art.size != tuple(size):  # the client stretches a button's art to the button
                art = art.resize(tuple(size), Image.BILINEAR)
            layer.alpha_composite(art, at)
        if templates.find('NormalDecal') is not None:
            # An effect slot's and a book slot's spell are A_SpellIcons cells, scaled to the decal.
            kind = 'item' if screen_id in ITEM_DECALS else 'A_SpellIcons'
            cell = (SPELL_ICONS[effect] if effect is not None else 14 if screen_id in ITEM_DECALS
                    else self.book_cell(screen_id))
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
        """The sample effect on an effect slot (its name label's), else None."""
        if not (screen_id.startswith('Buff') and screen_id[4:].isdigit()):
            return None
        labels = [e for e in defined.values() if e.tag == 'Label' and e.findtext('ScreenID') == f'{screen_id}Label']
        eq_type = labels[0].findtext('EQType') if labels else None
        return LABELS.get(int(eq_type)) if eq_type else None

    @staticmethod
    def book_cell(screen_id):
        """A spell book slot's icon, or None for an empty slot or any other button."""
        n = screen_id[len('SBW_Spell'):]
        return BOOK[int(n)][1] if screen_id.startswith('SBW_Spell') and n.isdigit() and int(n) < len(BOOK) else None

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
        banked = (skin.BANK_SLOT_TYPE <= eq_type < skin.BANK_SLOT_TYPE + BANK_ITEMS
                  or skin.SHARED_SLOT_TYPE <= eq_type < skin.SHARED_SLOT_TYPE + SHARED_ITEMS)
        inspected = eq_type - skin.INSPECT_SLOT_TYPE in INSPECTED_SLOTS
        held = merchant or bag or given or offered or looted or banked or inspected or eq_type in HELD_SLOTS
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
        icon = self.icon('A_SpellGems', cell, (skin.GEM_ICON, skin.GEM_ICON))
        if icon is not None:
            layer.alpha_composite(icon, (at[0] + number(element, 'SpellIconOffsetX'),
                                         at[1] + number(element, 'SpellIconOffsetY')))

    def draw_editbox(self, layer, element, at, size, *_):
        """One line centered down the box, or a multiline box's text wrapped from its top, like an STMLbox's."""
        size_n = number(element, 'Font', 3)
        text = EDIT_TEXT.get(element.findtext('ScreenID') or '', '')
        line = LINE_HEIGHT.get(size_n, 14)
        clip = Image.new('RGBA', size, (0, 0, 0, 0))
        if flag(element, 'Style_Multiline'):
            for n, part in enumerate(wrapped(text, self.font(size_n), size[0])):
                self.text(clip, (0, n * line), part, size_n, color(element, 'TextColor'))
        else:
            self.text(clip, (0, (size[1] - line) // 2), text, size_n, color(element, 'TextColor'))
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
        row_colors = LIST_RGB.get(element.findtext('ScreenID') or '', [])
        for r, cells in enumerate(rows):
            x = 0
            for (_, width, _), text in zip(columns, cells):
                if width:
                    cell = Image.new('RGBA', (width, line), (0, 0, 0, 0))
                    self.text(cell, (0, 0), text, size_n, row_colors[r] if r < len(row_colors) else rgb)
                    clip.alpha_composite(cell, (x, header + r * line))
                x += width
        if flag(element, 'Style_VScroll'):
            self.scrollbar(clip, element.findtext('DrawTemplate'), header + len(rows) * line)
        layer.alpha_composite(clip, at)

    def draw_combobox(self, layer, element, at, size, *_):
        """A closed dropdown: its template's box, the chosen choice (COMBO_TEXT) and its arrow at the right inside the
        border. Where the client puts the text and the arrow isn't known: the text COMBO_TEXT_INSET in and centered down
        like an edit box's, the arrow at its art's size, centered down."""
        clip, (_, _, right, _) = self.frame(element.findtext('DrawTemplate') or '', *size,
                                           border=flag(element, 'Style_Border'))
        size_n = number(element, 'Font', 3)
        self.text(clip, (COMBO_TEXT_INSET, (size[1] - LINE_HEIGHT.get(size_n, 14)) // 2),
                  COMBO_TEXT.get(element.findtext('ScreenID') or '', ''), size_n, color(element, 'TextColor'))
        button = self.templates.get(element.findtext('Button') or '')
        arrow = self.art(button.findtext('Normal') or '') if button is not None else None
        if arrow is not None:
            clip.alpha_composite(arrow, (size[0] - right - arrow.width, (size[1] - arrow.height) // 2))
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
        # The pages start the tab border's LeftBottom height above the tab row's bottom, down by the page border's Top
        # height, which differs between our page borders (see LIST_PAGE_BORDER).
        border = self.templates.get(element.findtext('PageBorderTemplate') or '')
        top_piece = self.art(border.findtext('Top')) if border is not None else None
        top = skin.TAB_ROW_HEIGHT - skin.TAB_OVERLAP + (top_piece.height if top_piece is not None else skin.PAGE_TOP_GAP)
        area = (size[0] - 2 * skin.LEFT, size[1] - top)
        self.pieces(layer, [p.text for p in pages[page].findall('Pieces')], defined,
                    (at[0] + skin.LEFT, at[1] + top), area, state, page)

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

    def spell_icon_sheet(self, compare=None, scale=3):
        """Every spell icon with a picture, numbered: at 40px (the book and item window), at 24px (the gems) and at 16
        (the 40 scaled, as in the Effects rows), after compare's own cell when given (a skin's folder, read for its
        pictures' ideas). Then each tile once, plain, as the cells with no picture yet show it."""
        tiles = [(tile, next((c for c in cells if c not in skin.SPELL_PICTURES), None))
                 for tile, cells in skin.SPELL_TILE_CELLS.items()]
        entries = [(str(cell), cell) for cell in sorted(skin.SPELL_PICTURES)] + [(t, c) for t, c in tiles if c is not None]
        sizes = [skin.BOOK_ICON, skin.GEM_ICON, skin.ROW_ICON]
        block = (skin.BOOK_ICON if compare else 0) + sum(sizes) + MARGIN * (len(sizes) + (1 if compare else 0))
        columns, row = 6, skin.BOOK_ICON + 2 * MARGIN
        rows = -(-len(entries) // columns)
        sheet = Image.new('RGBA', (columns * block + MARGIN, rows * row + MARGIN), skin.PANEL_RGBA)
        draw = ImageDraw.Draw(sheet)
        for n, (label, cell) in enumerate(entries):
            x, y = MARGIN + n % columns * block, MARGIN + n // columns * row
            draw.text((x, y - MARGIN + 1), label, font=self.font(1), fill=(*skin.TEXT_RGB, 255))
            big = self.grid_cell('A_SpellIcons', cell) if cell < skin.SPELL_ICON_CELLS else None
            images = [compare_cell(compare, cell)] if compare else []
            images += [big, self.grid_cell('A_SpellGems', cell),
                       big.resize((skin.ROW_ICON, skin.ROW_ICON), Image.BILINEAR) if big else None]
            for image, side in zip(images, ([skin.BOOK_ICON] if compare else []) + sizes):
                if image is not None:
                    sheet.alpha_composite(image.convert('RGBA'), (x, y + (skin.BOOK_ICON - image.height) // 2))
                x += side + MARGIN
        return sheet.resize((sheet.width * scale, sheet.height * scale), Image.NEAREST)

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


def compare_cell(folder, cell):
    """A skin's own picture for a spell icon cell, from its stock-named sheets in folder: its 40px spells01 to 05.tga,
    or past them its 24px gemicons01 and 02.tga. None when it has none."""
    size, per_sheet, pattern = ((skin.BOOK_ICON, 36, 'spells{:02}.tga') if cell < skin.SPELL_ICON_CELLS
                                else (skin.GEM_ICON, 100, 'gemicons{:02}.tga'))
    sheet, spot = divmod(cell, per_sheet)
    path = skin.find_file(Path(folder), pattern.format(sheet + 1))
    if path is None:
        return None
    across = skin.ICON_SHEET // size
    x, y = spot % across * size, spot // across * size
    return Image.open(path).convert('RGBA').crop((x, y, x + size, y + size))


def skin_folder(name, eq_dir=None):
    """uifiles/<name> in the EverQuest folder, or None."""
    for folder in [Path(eq_dir)] if eq_dir else [Path(d) for d in EQ_DIRS if d]:
        if (folder / 'uifiles' / name).is_dir():
            return folder / 'uifiles' / name
    return None


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
    parser.add_argument('--eq', type=Path, help='an EverQuest folder, for the stock item icons')
    parser.add_argument('--compare', metavar='SKIN', help='with icons: that skin\'s own picture beside each spell icon')
    args = parser.parse_args(argv)
    icons = any(word.lower() == 'icons' for word in args.windows)
    words = [word for word in args.windows if word.lower() != 'icons']
    names = chosen(words) if words or not icons else []
    preview = Preview(skin_files(args.out), args.eq)
    for path in save(preview, names, args.out, args.state, args.scale):
        print(path)
    if icons:
        compare = skin_folder(args.compare, args.eq) if args.compare else None
        if args.compare and compare is None:
            raise SystemExit(f'No skin folder uifiles/{args.compare} in the EverQuest folder')
        path = Path(args.out) / ICON_SHEET_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        preview.spell_icon_sheet(compare, args.scale).save(path)
        print(path)


if __name__ == '__main__':
    main()
