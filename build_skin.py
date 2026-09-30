"""TriageUI: EverQuest windows for Project Quarm in the look of EQ Triage's overlays.

The script writes a skin folder of TriageUI's own windows and art. For everything else the game falls
back to its own UI files (uifiles/default), so every window TriageUI hasn't redesigned keeps EverQuest's
own look; --base builds it on another skin of yours instead. It uses only the standard library, and it
never changes the skin it reads.

Copyright 2026 Sebik <Europa>, licensed under CC BY-NC-SA 4.0: see LICENSE.
"""

import argparse
import math
import re
import shutil
import struct
import sys
from pathlib import Path
from xml.sax.saxutils import escape

SKIN_NAME = 'TriageUI'
# The release's version, the only place it's set: README's first line shows it and tools/release.py checks it
# against the git tags.
VERSION = '1.0.0'
DEFAULT_EQ_DIR = Path(r'C:\QUARM')
# The game's own UI files. The client falls back to them file by file, so a build on them copies nothing: the skin
# is only TriageUI's files, and nothing in it comes from another skin.
DEFAULT_BASE = 'default'
# Written into every folder this script builds, so a rebuild only ever replaces its own output.
MARKER_FILE = 'TriageUI.txt'
# LICENSE's credit and terms, in every XML file the build writes and in MARKER_FILE, so they go along with any one
# file shared alone. ASCII, with no -- or angle brackets, so it can stand in an XML comment.
LICENSE_NOTICE = ('TriageUI (github.com/CopperGlade/TriageUI), copyright 2026 Sebik (Europa), licensed under '
                  'CC BY-NC-SA 4.0: https://creativecommons.org/licenses/by-nc-sa/4.0/')

# The client seems to keep our 32-bit art as 16-bit textures, 16 steps per channel (eqclient.ini has
# TextureQuality=1), and dithers any value between two steps into a pattern: the buttons' see-through
# hover and their edges showed one in game. A dither shows where a step changes the brightness a lot:
# in alpha, which blends a pixel with what's behind it, and in green, which carries most of a color's
# brightness. Red and blue carry so little that a dither between their steps can't be seen, so they
# keep EQ Triage's colors exact (snapping them too turned its panel (14, 18, 26) indigo).
STEP = 17
SNAPPED_CHANNELS = (1, 3)  # green and alpha


def snapped(rgba):
    """rgba with its green and alpha on the nearest of the 16 steps a 16-bit texture holds exactly."""
    return tuple(round(c / STEP) * STEP if i in SNAPPED_CHANNELS else c for i, c in enumerate(rgba))


# The overlays' look, copied from EQ Triage (triage.py) so the windows match them.
PANEL_RGB = (14, 18, 26)
# The panel is opaque: players set each window's own alpha and fade in game, which a baked-in opacity
# (85% at first) only stacked with (the user's call). Opaque also leaves nothing to dither.
OPACITY = 1.0
EDGE_RGBA = (255, 255, 255, 50)
TEXT_RGB = (232, 232, 232)  # the overlay's normal row text, '#e8e8e8'
PET_RGB = (138, 138, 138)  # the overlay's grey, '#8a8a8a'
# The casting window's text and bar, apart from the target's: a soft red, '#e88080' (the user's pick; a soft
# green, '#8fd19e', at first). The user tried it on the target window instead, with the casting window
# white, and came back to this.
SPELL_RGB = (232, 128, 128)
MANA_RGB = (120, 165, 235)  # the mana bar: a soft blue, so mana reads apart from HP (the user's pick)
# The air window's caption and bar: a soft cyan, '#80d8e8', the stock bar's cyan toned down like the casting
# red (the user's pick).
AIR_RGB = (128, 216, 232)
# The group window's member names and health %: the mana bar's soft blue, which the user asked to try, as the
# members didn't read well in the text's white.
GROUP_RGB = MANA_RGB
# A solid bar in the text's color looks much brighter than thin letters, so bars are drawn at about
# 70% (170, the nearest step), which the user found less harsh.
BAR_FILL = snapped((255, 255, 255, round(255 * 0.7)))  # colored by FillTint
CORNER_RADIUS = 3
PADDING = 6

# The panel and edge as drawn: green on a step, so (14, 18, 26) becomes (14, 17, 26).
PANEL_RGBA = snapped((*PANEL_RGB, round(255 * OPACITY)))
EDGE_FADED = snapped((*EDGE_RGBA[:3], round(EDGE_RGBA[3] * OPACITY)))
WHITE = (255, 255, 255, 255)
# Fully transparent pixels keep the panel's color, so filtering at a corner never darkens it.
CLEAR = (*PANEL_RGBA[:3], 0)
# Button styles: (fill, edge, text) in the Normal state. Wash is the white wash over the panel, with its
# own per-state (fill, edge) in BUTTON_LOOKS; the solid styles go BUTTON_HOVER_STEPS lighter on hover,
# BUTTON_PRESS_STEPS darker when pressed and fade when disabled. The user found the wash hard to see ("a
# strange pattern"), so the solid ones were shown in the group window to pick from; the user had them
# removed and kept the wash. Art colors are multiples of 17 (see BUTTON_LOOKS).
BUTTON_STYLES = {
    'Wash': ((255, 255, 255, 17), (255, 255, 255, 51), TEXT_RGB),
    'Light': ((221, 221, 221, 255), (102, 102, 119, 255), (20, 24, 30)),
    'Soft': ((170, 170, 187, 255), (68, 68, 85, 255), (14, 18, 26)),
    'Slate': ((68, 85, 102, 255), (34, 34, 51, 255), TEXT_RGB),
    'Dark': ((34, 34, 51, 255), (136, 136, 153, 255), TEXT_RGB),
}
BUTTON_HOVER_STEPS = 2
BUTTON_PRESS_STEPS = 1
BUTTON_STYLE = 'Wash'  # every button's style
# The wash's (fill, edge) per state. Its see-through white hover showed "some sort of pattern" in game:
# either the game showing through, or the client keeping our art as a 16-bit texture, 16 steps per
# channel, and dithering a faint alpha between two steps. So hovered and pressed are opaque slate, and
# every button color sits on those steps (multiples of 17, see snapped()), leaving nothing to dither.
BUTTON_LOOKS = {
    'Normal': (BUTTON_STYLES['Wash'][0], BUTTON_STYLES['Wash'][1]),
    'Flyby': ((51, 68, 85, 255), (102, 119, 136, 255)),  # '#334455', edge '#667788'
    'Pressed': ((34, 51, 68, 255), (85, 102, 119, 255)),  # '#223344', edge '#556677'
    'Disabled': ((255, 255, 255, 0), (255, 255, 255, 34)),
}
# The art each button state uses; pressed and hovered looks pressed.
BUTTON_ART = {'Normal': 'Normal', 'Pressed': 'Pressed', 'Flyby': 'Flyby', 'Disabled': 'Disabled',
              'PressedFlyby': 'Pressed'}

# The frame is 4px thick (the 1px edge plus panel) so the rounded corner fits inside its corner piece.
BORDER = 4
SUPERSAMPLE = 16
PIECE_LENGTH = 4  # the length of the frame's straight pieces, which the client repeats along each side
# Both sides stay powers of two, and no side longer than 1024, the height the game has shown. 256 wide ran out of room
# with the raid window's buttons, 512 with the tracking window's filters.
ATLAS_WIDTH = 1024
ATLAS_HEIGHT = 1024  # room for every button's art with its label drawn in, and every icon's in each state
BACKGROUND_SIZE = 16

PIECES_TEXTURE = 'triageui_pieces.tga'
BACKGROUND_TEXTURE = 'triageui_bg.tga'
PERCENT_TEXTURE = 'triageui_percent.tga'
FIELD_TEXTURE = 'triageui_field.tga'  # the chat input's strip, darker than the panel
GUTTER_TEXTURE = 'triageui_gutter.tga'  # the scrollbar's track: clear, so only the thumb shows
DIVIDER_TEXTURE = 'triageui_divider.tga'  # the row divider's color, for a divider standing up (see DIVIDER_TEMPLATE)
# The skin's copy of the base's EQUI_Animations.xml carries our shared definitions: the client loads it
# before every window file, so every window can use them.
ANIMATIONS_FILE = 'EQUI_Animations.xml'
GROUP_FILE = 'EQUI_GroupWindow.xml'
TARGET_FILE = 'EQUI_TargetWindow.xml'
CASTING_FILE = 'EQUI_CastingWindow.xml'
BREATH_FILE = 'EQUI_BreathWindow.xml'  # the air window: duxaUI has none, so it was default's
CHAT_FILE = 'EQUI_ChatWindow.xml'

# Layout. Positions inside a window are relative to the area inside the frame. EQ's built-in fonts run
# from 0 (small) to 6 (large), with nothing in between; the user likes 3. Button labels are our own
# lettering instead (see LABEL_GLYPHS): 2 looked squished, 3 too big. The dialogs' buttons and the give, trade
# and loot windows' show their names in font 2 on taller buttons instead (see add_text_buttons()): the lettering
# read too small there (the user's call). So does Close, painted in font 2's look (see CLOSE_INK).
TEXT_FONT = 3
WINDOW_WIDTH = 200  # the group and casting windows; the target window is narrower
LEFT = PADDING - BORDER
RIGHT = WINDOW_WIDTH - 2 * BORDER - LEFT
TEXT_HEIGHT = 14
BAR_TOP = 16  # under a line of text; also SIDL's default GaugeOffsetY
BAR_HEIGHT = 4
BOTTOM_GAP = 2
# The target window's width follows the user's requests: 20% narrower than the others, then 10% wider.
# The name has the whole first line, since some mobs have long names; the second line has the bar,
# then the health % (a number on the left looked wrong to the user). Both lines share the name's
# padding, which the user likes, and at 100% the gap between the bar and the number is the same.
TARGET_WIDTH = WINDOW_WIDTH * 4 // 5 * 11 // 10
TARGET_RIGHT = TARGET_WIDTH - 2 * BORDER - LEFT
TARGET_LINE2 = TEXT_HEIGHT  # straight under the name, without extra spacing (the user removed it)
# Every health readout: "100" and "%" in font 3, measured in Arial at 12px (13px is a pixel wider each).
# The number is right-aligned in exactly its width and the drawn % follows it, ending at the padding.
NUMBER_WIDTH = 21
PERCENT_WIDTH = 11
TARGET_HEIGHT = 2 * BORDER + TARGET_LINE2 + TEXT_HEIGHT
# The target's health bar is thinner than the other bars, centered on the digits beside it, and ends a
# padding's width before the number. Its track shows its full length however low the health gets (the
# user dropped the end marks tried before it). The casting window is the target window's twin at the
# user's request: as wide and as tall, with the same bar on its second line, as if there were text there
# to center it on.
def health_bar_width(right):
    """A health bar's width in a window whose readout ends at right: the bar ends a padding's width before
    the number."""
    return right - PERCENT_WIDTH - NUMBER_WIDTH - PADDING - LEFT


TWIN_BAR_WIDTH = health_bar_width(TARGET_RIGHT)
# 3px, grown from 2 at the bottom: a centered pixel can't split, and 1px higher had looked too high.
TWIN_BAR_HEIGHT = 3
TWIN_BAR_TOP = TARGET_LINE2 + 7
# The % is drawn rather than typed, so it can hide while nothing is targeted (typed text always shows).
# It copies Arial's % at 12px, the closest match to font 3: PERCENT_WIDTH wide, 9px tall, its top
# PERCENT_INK_TOP + PERCENT_SUBPIXEL down its line. The user tried 2, 3, 4, 3.5 and 3 in game and found
# 3.5 perfect. The half pixel draws the glyph that much lower inside a spot one row taller, which
# softens its horizontal edges a little. Two small rings and a slash, each GLYPH_STROKE thick.
PERCENT_INK_TOP = 3
PERCENT_SUBPIXEL = 0.5
PERCENT_GLYPH_HEIGHT = 9 + math.ceil(PERCENT_SUBPIXEL)
GLYPH_STROKE = 1.15
PERCENT_RINGS = ((2.4, 2.4), (8.6, 6.6))  # centers; each ring is 1.75 x 2.0 across its radii
PERCENT_RING_RADII = (1.75, 2.0)
PERCENT_SLASH = ((8.3, 0.3), (2.7, 8.7))
# Zeal's server tick (gauge 24, which Zeal fills in any window): it drains to empty at each tick, when mana
# comes in, so it sits TICK_GAP under the mana bar (see MANA_TICK_TOP), where casters look while they med.
# Solid, in the text's white, with no track (the user's picks): the health and mana bars have their own colors,
# and the casting bar's soft red, beside the mana bar's blue, hurt the eyes. Two clear pixels under the bar: with
# one, the two read as touching. Along the top of the target window, players didn't notice it, in the overlay's
# grey, the mana bar's blue or the tracks' faint color; along the top border it didn't show, since the client
# draws nothing outside a window's inside area.
TICK_TYPE = 24
TICK_HEIGHT = 2
TICK_GAP = 2
TICK_RGB = TEXT_RGB
# Things shown only with a target are a target health gauge whose fill, this wide, is clipped to the
# thing's spot. The client draws a fill's width times the gauge's value, so any health above 0 shows
# the whole spot, and no target (value 0) shows nothing. duxaUI colors its bars the same way.
SHOWN_REACH = 10000
# "Casting:" and a space in font 3 (Arial at 12 and 13px measured 48 to 52); the spell name follows.
CASTING_PREFIX_WIDTH = 50
CAST_BAR_WIDTH = TARGET_RIGHT - LEFT  # the casting bar, across the whole width (the user's request)
# The group window: each member's line, name and health %, with a thin bar under the name, then their pet's
# line, indented, with a thin bar too: the client gives no number for a pet's health. Each line stays a
# full-width gauge, so all of it can be clicked.
GROUP_SIZE = 5
# GROUP_WIDTH and its RIGHT and CONTENT_WIDTH, and GROUP_BAR_WIDTH, are set with the pet window's constants:
# the group window is as wide as the pet window (the user's call), and its pets' bars as long as that window's.
PET_INDENT = 12
PET_BAR_HEIGHT = 2
# Pets' names in the smaller font 2, on a shorter line, so the window is less tall (the user's call).
PET_FONT = 2
PET_TEXT_HEIGHT = 12
PET_BAR_GAP = 1  # between the pet's name and its bar (the user asked for a pixel more)
PET_HEIGHT = PET_TEXT_HEIGHT + PET_BAR_GAP + PET_BAR_HEIGHT
# A member's bar is like their pet's, a pixel under the name and solid in the names' soft blue as a pet's is in
# its grey (the user loved the contrast and asked for it; members had no bar before, to keep the window short).
MEMBER_BAR_TOP = TEXT_HEIGHT + PET_BAR_GAP
MEMBER_LINE_HEIGHT = MEMBER_BAR_TOP + PET_BAR_HEIGHT
CAPTION_INK_TOP = 2  # font 2's capitals (pets' names, captions) start about this far into their line (Arial 10px)
# The pet's line a padding under the member's bar, to its name's ink (the user's pick over straight under it).
PET_TOP = MEMBER_LINE_HEIGHT + PADDING - CAPTION_INK_TOP
MEMBER_HEIGHT = PET_TOP + PET_HEIGHT  # a member's rows, down to their pet's bar
# Members are divided by the Effects window's row divider (the user asked for the same), a padding under
# the pet row above and a padding over the ink of the next member's name, which starts TEXT_INK_TOP into
# its line (rounded up to a whole pixel). They always show, like the Effects window's.
TEXT_INK_TOP = PERCENT_INK_TOP + PERCENT_SUBPIXEL
DIVIDER_HEIGHT = 1
DIVIDER_TO_NAME = math.ceil(PADDING - TEXT_INK_TOP)
MEMBER_PITCH = MEMBER_HEIGHT + PADDING + DIVIDER_HEIGHT + DIVIDER_TO_NAME
# Between buttons side by side, between rows of buttons, and between what's above and the first row:
# the window's own side padding, at the user's request, so the spacing reads as one system.
BUTTON_GAP = PADDING
BUTTON_ROW_GAP = PADDING
BUTTON_HEIGHT = 16
# BUTTON_WIDTH, the group window's buttons', is set with the group window's width, below.
# Button labels are drawn into the buttons' art in our own pixel lettering: the client's font 2 looked
# squished, font 3 too big, and a skin can't space a font's letters. Each glyph is 7 rows sitting on the
# last, '#' for ink, 1px strokes; lowercase letters start at row 2, and p, g and y have an 8th row, below the
# line, for their tails. Letters are LETTER_SPACING apart (the user asked for more room than the font gave) and each label
# is centered in its button, its x-height on the button's middle.
LETTER_SPACING = 2
LABEL_HEIGHT = 7
LABEL_TOP = (BUTTON_HEIGHT - LABEL_HEIGHT) // 2
LABEL_GLYPHS = {
    'A': ('.###.', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'),
    'B': ('####.', '#...#', '#...#', '####.', '#...#', '#...#', '####.'),
    'C': ('.###.', '#...#', '#....', '#....', '#....', '#...#', '.###.'),
    'D':('####.', '#...#', '#...#', '#...#', '#...#', '#...#', '####.'),
    # 5 wide, unlike F: the compass's N, E, S and W all are, so each label centers exactly on its mark (see
    # COMPASS_MARKS).
    'E': ('#####', '#....', '#....', '####.', '#....', '#....', '#####'),
    'F': ('####', '#...', '#...', '###.', '#...', '#...', '#...'),
    'G': ('.###.', '#...#', '#....', '#.###', '#...#', '#...#', '.###.'),
    'I': ('#', '#', '#', '#', '#', '#', '#'),
    'L': ('#...', '#...', '#...', '#...', '#...', '#...', '####'),
    'M': ('#...#', '##.##', '#.#.#', '#.#.#', '#...#', '#...#', '#...#'),
    'N': ('#...#', '##..#', '#.#.#', '#.#.#', '#..##', '#...#', '#...#'),
    'O': ('.###.', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'),
    'R': ('####.', '#...#', '#...#', '####.', '#.#..', '#..#.', '#...#'),
    'S': ('.###.', '#...#', '#....', '.###.', '....#', '#...#', '.###.'),
    'T': ('#####', '..#..', '..#..', '..#..', '..#..', '..#..', '..#..'),
    'W': ('#...#', '#...#', '#...#', '#.#.#', '#.#.#', '##.##', '#...#'),  # M upside down
    'a': ('....', '....', '.##.', '...#', '.###', '#..#', '.###'),
    'b': ('#...', '#...', '###.', '#..#', '#..#', '#..#', '###.'),
    'c': ('...', '...', '.##', '#..', '#..', '#..', '.##'),
    'd': ('...#', '...#', '.###', '#..#', '#..#', '#..#', '.###'),
    'e': ('....', '....', '.##.', '#..#', '####', '#...', '.###'),
    # Their bowls a row up, so the tail can hook under the line: a straight stem would make g read as q.
    'g': ('....', '....', '.###', '#..#', '#..#', '.###', '...#', '.##.'),
    'h': ('#...', '#...', '###.', '#..#', '#..#', '#..#', '#..#'),
    'i': ('#', '.', '#', '#', '#', '#', '#'),
    'k': ('#...', '#...', '#..#', '#.#.', '##..', '#.#.', '#..#'),
    'l': ('#', '#', '#', '#', '#', '#', '#'),
    'm': ('.....', '.....', '####.', '#.#.#', '#.#.#', '#.#.#', '#.#.#'),
    'n': ('....', '....', '###.', '#..#', '#..#', '#..#', '#..#'),
    'o': ('....', '....', '.##.', '#..#', '#..#', '#..#', '.##.'),
    # A row below the line for its stem: kept on the line, it read as a small capital P.
    'p': ('....', '....', '###.', '#..#', '#..#', '#..#', '###.', '#...'),
    'r': ('...', '...', '#.#', '##.', '#..', '#..', '#..'),
    's': ('....', '....', '.###', '#...', '.##.', '...#', '###.'),
    't': ('.#.', '.#.', '###', '.#.', '.#.', '.#.', '..#'),
    'u': ('....', '....', '#..#', '#..#', '#..#', '#..#', '.###'),
    'v': ('.....', '.....', '#...#', '#...#', '.#.#.', '.#.#.', '..#..'),
    'w': ('.....', '.....', '#...#', '#...#', '#.#.#', '#.#.#', '.#.#.'),
    'y': ('....', '....', '#..#', '#..#', '#..#', '.###', '...#', '.##.'),
    ' ': ('..', '..', '..', '..', '..', '..', '..'),  # with the spacing either side, words are 6px apart
}
LABEL_ALPHA = {'Normal': 255, 'Flyby': 255, 'Pressed': 255, 'Disabled': 119}
# The group window's buttons: (ScreenID, label, column). The client shows Follow and Decline in place of
# Invite and Disband while you have an invitation. duxaUI's LFG button is left out at the user's request.
GROUP_BUTTONS = (('InviteButton', 'Invite', 0), ('FollowButton', 'Follow', 0),
                 ('DisbandButton', 'Disband', 1), ('DeclineButton', 'Decline', 1))
# The hot button window's grid (see HOTBUTTON_FILE), set here since the pet, group and Actions windows take
# its width.
HOT_SIZE = 36
HOT_COLUMNS = 4
HOT_WIDTH = 2 * PADDING + HOT_COLUMNS * HOT_SIZE + (HOT_COLUMNS - 1) * BUTTON_GAP
# The pet window: the target window's shape, the pet's name on the first line, the bar and HP % on the
# second, then its commands in three columns of two, each column a pair of related ones stacked so they
# read together (the user's idea): Attack over Back (fight, stop fighting), Guard over Follow (hold a
# spot, stop holding it), Taunt (the user's most-clicked) over Dismiss (the default skin's "Go Away" was
# a bit too wide for the button in game). Columns and pairs are a padding apart. The window is as wide as
# the hot button window (the user's call; it was a pixel wider than the target's before), and the three
# columns fill its row exactly. Sit, which nobody uses, is hidden.
PET_WINDOW_FILE = 'EQUI_PetInfoWindow.xml'
PET_COLUMNS = (  # each column top to bottom: (ScreenID, text, tooltip), the tooltips the default skin's
    (('AttackButton', 'Attack', 'Pet Attack'), ('BackButton', 'Back', 'Pet Back Off')),
    (('GuardButton', 'Guard', 'Pet Guard Here'), ('FollowButton', 'Follow', 'Pet Follow Me')),
    (('TauntButton', 'Taunt', 'Pet Taunt'), ('LostButton', 'Dismiss', 'Pet Get Lost')),
)
PET_HIDDEN = ('SitButton',)  # the client looks these up, so they stay in the window, unseen
PET_PAIR_GAP = BUTTON_ROW_GAP  # 2, 3 and 4 looked cramped in game
PET_WIDTH = HOT_WIDTH
PET_RIGHT = PET_WIDTH - 2 * BORDER - LEFT
PET_BUTTON_WIDTH = (PET_RIGHT - LEFT - (len(PET_COLUMNS) - 1) * BUTTON_GAP) // len(PET_COLUMNS)
PIW_BAR_WIDTH = health_bar_width(PET_RIGHT)  # two pixels shorter than the target's, keeping its gaps
# Measured from the bottom of the health line's ink: the HP number and the drawn %, whose bottom matches
# the digits', hang 3px below the bar, and the user found the buttons too close under them.
PET_BUTTONS_TOP = TARGET_LINE2 + PERCENT_INK_TOP + PERCENT_GLYPH_HEIGHT + BUTTON_ROW_GAP
# The group window is as wide as the pet window, and so the hot button window (the user's call; 20% narrower
# than the others before).
GROUP_WIDTH = PET_WIDTH
GROUP_RIGHT = GROUP_WIDTH - 2 * BORDER - LEFT
GROUP_CONTENT_WIDTH = GROUP_RIGHT - LEFT
# The pets' bars end where the pet window's bar does, a padding before the members' HP numbers (the user's pick
# when the window went to the hot button window's width; as long as the target window's before).
GROUP_BAR_WIDTH = PIW_BAR_WIDTH
# The group window's two buttons fill its row with a gap between. The row splits evenly; were its width odd,
# the second button would take the extra pixel rather than leave it at the edge (both gaps stay PADDING).
BUTTON_WIDTH = (GROUP_CONTENT_WIDTH - BUTTON_GAP) // 2
GROUP_BUTTON_WIDTHS = (BUTTON_WIDTH, GROUP_CONTENT_WIDTH - BUTTON_GAP - BUTTON_WIDTH)
# Every labeled button in use, by size: each gets its own art, drawn at its own size with its label in it.
BUTTON_LABELS = {}
for _screen_id, _label, _column in GROUP_BUTTONS:
    _size = (GROUP_BUTTON_WIDTHS[_column], BUTTON_HEIGHT)
    BUTTON_LABELS[_size] = BUTTON_LABELS.get(_size, ()) + (_label,)
BUTTON_LABELS[(PET_BUTTON_WIDTH, BUTTON_HEIGHT)] = tuple(label for column in PET_COLUMNS for _, label, _ in column)


def add_text_buttons(widths):
    """Plain art, with no label of ours, for buttons at each of widths and TEXT_BUTTON_HEIGHT tall whose names are
    their own text in ACTION_FONT (see button()), as the confirmation dialog's are."""
    for width in widths:
        key = (width, TEXT_BUTTON_HEIGHT)
        if '' not in BUTTON_LABELS.get(key, ()):
            BUTTON_LABELS[key] = BUTTON_LABELS.get(key, ()) + ('',)


# The window selector: the buttons that open and close the other windows, one row of square toggles,
# each with a line icon drawn here, with the default skin's tooltips, Options and Inventory first and the
# rest in the default skin's order. A toggle shows
# Pressed while its window is open. Everything is PADDING apart and PADDING from the window's edge.
SELECTOR_FILE = 'EQUI_SelectorWnd.xml'
SELECTOR_BUTTONS = (  # (ScreenID, tooltip, icon), Options then Inventory first (the user's order)
    ('SELW_OptionsToggleButton', 'Options', 'Options'),
    ('SELW_InventoryToggleButton', 'Inventory', 'Inventory'),
    ('SELW_ActionsToggleButton', 'Actions', 'Actions'),
    ('SELW_FriendsToggleButton', 'Friends', 'Friends'),
    ('SELW_HotboxToggleButton', 'Hotbuttons', 'Hotbuttons'),
    ('SELW_CastSpellToggleButton', 'Spells', 'Spells'),
    ('SELW_PetInfoToggleButton', 'Pet Info', 'Pet'),
    ('SELW_BuffToggleButton', 'Effects', 'Effects'),
)
SELECTOR_HIDDEN = ('SELW_HelpToggleButton',)  # the user had Help removed; the client still looks it up
TOGGLE_SIZE = 26
ICON_SIZE = 16
ICON_STROKE = 1.5
ICON_RGB = (238, 238, 238)  # the text's color, on the 16 steps (see BUTTON_LOOKS)
# Each toggle state's (fill, edge, icon alpha): closed, the buttons' faint wash with a dimmer icon, and
# slate when hovered; open, a lighter slate with a brighter outline, lighter still when hovered.
TOGGLE_LOOKS = {
    'Normal': (*BUTTON_LOOKS['Normal'], 187),
    'Flyby': (*BUTTON_LOOKS['Flyby'], 255),
    'Pressed': ((68, 85, 102, 255), (136, 153, 170, 255), 255),  # '#445566', edge '#8899aa'
    'PressedFlyby': ((85, 102, 119, 255), (153, 170, 187, 255), 255),  # '#556677', edge '#99aabb'
}
TOGGLE_ART = {'Normal': 'Normal', 'Pressed': 'Pressed', 'Flyby': 'Flyby', 'Disabled': 'Normal',
              'PressedFlyby': 'PressedFlyby'}  # never disabled, as in the default skin
SELECTOR_WIDTH = 2 * PADDING + len(SELECTOR_BUTTONS) * TOGGLE_SIZE + (len(SELECTOR_BUTTONS) - 1) * BUTTON_GAP
SELECTOR_HEIGHT = 2 * PADDING + TOGGLE_SIZE
# The icon buttons elsewhere (the Actions window's) also have a disabled look, which the client may use: no
# fill, a faint edge and a dim icon, like the labeled buttons' (BUTTON_LOOKS, LABEL_ALPHA).
ICON_LOOKS = {**TOGGLE_LOOKS, 'Disabled': (*BUTTON_LOOKS['Disabled'], LABEL_ALPHA['Disabled'])}
ICON_ART = {**TOGGLE_ART, 'Disabled': 'Disabled'}
# The Actions window: the stock tab box and its four pages, in the stock order, whose every control the
# client looks up by ScreenID (every skin here keeps them all). The tabs are the pages' icons as selector
# toggles, the open page's lit. On every page the actions are buttons in two columns filling the row (the
# user's design, after icon buttons, then full-width buttons one per row). The game writes the ability and
# social names itself; the Main and Combat pages' fixed names are the buttons' own text, in the same font.
ACTIONS_FILE = 'EQUI_ActionsWindow.xml'
# Each page's name is its tab's tooltip (the user asked for one on each tab), and the page's own: the stock
# tooltips were "Main Page" and so on; the user knows the middle two as general and combat skills.
ACTIONS_PAGES = (  # (item, ScreenID, name, tab icon)
    ('TUI_AW_MainPage', 'ActionsMainPage', 'Main', 'Main'),
    ('TUI_AW_AbilitiesPage', 'ActionsAbilitiesPage', 'General Skills', 'Abilities'),
    ('TUI_AW_CombatPage', 'ActionsCombatPage', 'Combat Skills', 'Combat'),
    ('TUI_AW_SocialsPage', 'ActionsSocialsPage', 'Socials', 'Socials'),
)
# Each page's buttons, a spot each, left to right then down as in the stock skin: (ScreenID, text), the text
# None where the game writes it. On the Main page the client shows one of a pair in one spot (Sit or Stand,
# Run or Walk, Invite or Follow), as in the stock skin. The user doesn't need Who or Disband, so they are
# hidden; the client still looks them up. Follow, the client's swap for Invite, shows only while you have a
# group invitation, and joins the group (the user asked for Follow first, alone, then for Invite too).
MAIN_SPOTS = (
    (('AMP_CampButton', 'Camp'),),
    (('AMP_SitButton', 'Sit'), ('AMP_StandButton', 'Stand')),
    (('AMP_RunButton', 'Run'), ('AMP_WalkButton', 'Walk')),
    (('AMP_InviteButton', 'Invite'), ('AMP_FollowButton', 'Follow')),
)
MAIN_HIDDEN = ('AMP_WhoButton', 'AMP_DisbandButton')
ORDINALS = ('First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth')
COMBAT_SPOTS = tuple((spot,) for spot in (
    ('ACP_MeleeAttackButton', 'Melee Attack'), ('ACP_RangeAttackButton', 'Range Attack'),
    *((f'ACP_{n}AbilityButton', None) for n in ORDINALS[:4])))
ABILITY_SPOTS = tuple(((f'AAP_{n}AbilityButton', None),) for n in ORDINALS)
SOCIALS = tuple(f'ASP_SocialButton{n}' for n in range(1, 13))
SOCIAL_ARROWS = (('ASP_SocialPageLeftButton', 'Previous Page', 'Left'),
                 ('ASP_SocialPageRightButton', 'Next Page', 'Right'))
SOCIAL_PAGE_LABEL = 'ASP_CurrentSocialPageLabel'
# As wide as the hot button window, like the pet and group windows (the user's call; 177 before, as they were).
# The buttons are in two columns across the row, the tabs filling the same row; both split evenly. The buttons
# are tall enough for font 3's line with room around it, but the names are in font 2, like the socials (the
# user asked for those first): at 78px, font 3's "Sense Heading" (about 85px) wouldn't fit.
ACTIONS_WIDTH = HOT_WIDTH
ACTIONS_CONTENT_WIDTH = ACTIONS_WIDTH - 2 * PADDING
TEXT_BUTTON_HEIGHT = 20
ACTION_FONT = 2
ACTION_COLUMNS = 2
_ACTION_SPAN = ACTIONS_CONTENT_WIDTH - (ACTION_COLUMNS - 1) * BUTTON_GAP
ACTION_WIDTHS = tuple(_ACTION_SPAN * (c + 1) // ACTION_COLUMNS - _ACTION_SPAN * c // ACTION_COLUMNS
                      for c in range(ACTION_COLUMNS))
ACTION_ROW_STEP = TEXT_BUTTON_HEIGHT + BUTTON_ROW_GAP
# Over the socials, the page arrows at either end, as tall as a button, and the page number between them,
# its digits' ink (3.5 to 12.5 down its line, like the drawn %'s) centered on the arrows.
ARROW_SIZE = TEXT_BUTTON_HEIGHT
DIGITS_INK_MIDDLE = PERCENT_INK_TOP + PERCENT_SUBPIXEL + (PERCENT_GLYPH_HEIGHT - math.ceil(PERCENT_SUBPIXEL)) / 2
SOCIAL_PAGE_LABEL_TOP = round(ARROW_SIZE / 2 - DIGITS_INK_MIDDLE)
SOCIALS_TOP = ARROW_SIZE + BUTTON_ROW_GAP
# The socials go down each column first, as in the stock skin (1 to 6, then 7 to 12). The bottom three rows
# (4, 5, 6, 10, 11 and 12) are hidden, to keep the window short (the user's calls: one row, to match the other
# pages when they were one button per row, then another once they were two columns, then a third, taking a
# row off the window); the client still looks those up, and their socials can't be clicked here.
SOCIAL_SLOT_ROWS = len(SOCIALS) // ACTION_COLUMNS  # the game's column of six
SOCIAL_ROWS = SOCIAL_SLOT_ROWS - 3  # the rows shown
# Every page is as tall as the tallest, the socials (the user asked for the window to be no taller).
ACTIONS_PAGE_HEIGHT = max(*(math.ceil(len(spots) / ACTION_COLUMNS) * ACTION_ROW_STEP
                            for spots in (MAIN_SPOTS, ABILITY_SPOTS, COMBAT_SPOTS)),
                          SOCIALS_TOP + SOCIAL_ROWS * ACTION_ROW_STEP) - BUTTON_ROW_GAP
# The tab box, from the window's inside top left, lays out its tabs and pages itself from its two border
# templates' pieces. The first build left most pieces out and crashed the game on load (an access violation
# at 0x593BE1, reading the tab border's missing Top), so this is read from eqgame.exe's tab box code:
# - The tab row starts at the box's font height + 8 tall; a taller tab icon makes it the icon's height plus
#   the tab border's Top height (the stock icons, 18px, never are, which is why no skin needed more).
# - Tab i gets an equal share of the box's width less the tab border's TopLeft and TopRight widths, from the
#   page border's TopLeft width in. Its icon is drawn at its own size at the share's top left, in by the tab
#   border's Left width and down by its Top height.
# - A closed page's tab is drawn TAB_SHIFT lower, and cut off the page border's Bottom height above the tab
#   row's bottom.
# - The pages start the tab border's LeftBottom height above the tab row's bottom, inset by the page border's
#   Top height, LeftTop and RightTop widths and Bottom height.
# - It reads the tab border's TopLeft, Top, TopRight, Left, Right and LeftBottom and the page border's
#   TopLeft, Top, LeftTop, RightTop and Bottom without checking they exist, so both templates have every piece
#   the stock ones have (the stock tab border has no bottom row).
# So the pieces are clear gaps sized for our layout: each tab's share is its tab and a padding, and an open
# page's tab art has its tab TAB_SHIFT lower than a closed one's, so every tab lands level. No piece can be 0
# tall, so the tabs sit a pixel further down than the padding (TAB_TOP).
# The tabs fill the row the buttons do, a padding apart (the user asked for wider tabs or more room between
# them). The shares split the row plus one padding as evenly as whole pixels allow (at this width exactly:
# TAB_WIDTHS 36 each), and the last share ends a padding after its tab, a TAB_CORNER in (no piece can be 0 wide), so the tab
# box runs TAB_OVERHANG past the window's inside on the right. Only clear space is there: the last tab's
# padding and the page border's right side.
TAB_BORDER = 'TUI_TabBorder'
PAGE_BORDER = 'TUI_PageBorder'
ACTIONS_INSIDE_WIDTH = ACTIONS_WIDTH - 2 * BORDER
TAB_TOP = 1  # the tab border's Top height
TAB_SHIFT = 2  # how much lower the client draws a closed page's tab
TAB_ART_HEIGHT = TOGGLE_SIZE + 2 * TAB_SHIFT  # room for the toggle either way up, never cut off
TAB_ROW_HEIGHT = TAB_TOP + TAB_ART_HEIGHT
TAB_OFFSET = 1  # the page border's TopLeft width: where the tabs start
TAB_ICON_INSET = LEFT - TAB_OFFSET  # the tab border's Left width: the first toggle at the window's padding
def tab_row(content_width, count):
    """count tabs filling a content row content_width wide from the window's padding, a padding apart, as the client
    lays them out: each gets an equal share of the row plus one padding (the client's own rounding), its tab and the
    padding after it. Returns the tabs' widths and their lefts in the window's inside."""
    shares_width = content_width + BUTTON_GAP
    shares = [shares_width * (i + 1) // count - shares_width * i // count for i in range(count)]
    return [share - BUTTON_GAP for share in shares], [LEFT + sum(shares[:i]) for i in range(count)]


TAB_SHARES_WIDTH = ACTIONS_CONTENT_WIDTH + BUTTON_GAP  # every tab and the padding after it
TAB_WIDTHS, TAB_LEFTS = tab_row(ACTIONS_CONTENT_WIDTH, len(ACTIONS_PAGES))
# The tab box shows no tooltip of a tab's own (the tabs aren't windows; its code has nothing for it), so each
# tab has an empty label over it carrying the page's name. Labels let clicks through to what's under them
# (duxaUI's effect names sit over the slot buttons, which still click off), so the tab still opens its page.
TAB_CORNER = 1  # the tab border's TopLeft and TopRight widths, which the shares leave out
TAB_BOX_WIDTH = TAB_SHARES_WIDTH + 2 * TAB_CORNER
TAB_OVERHANG = TAB_BOX_WIDTH - ACTIONS_INSIDE_WIDTH
# The page border's right side: to the padding. It comes to the padding and two TAB_CORNERs less LEFT whatever the
# row's width, so a tab box laid out the same way over another row (the AA window's) fits both templates as they are.
PAGE_RIGHT = TAB_BOX_WIDTH - LEFT - ACTIONS_CONTENT_WIDTH
TAB_OVERLAP = 1  # the tab border's LeftBottom height
TOGGLES_TOP = TAB_TOP + TAB_SHIFT  # where every tab lands, TOGGLE_SIZE tall
# Under the tabs, the Effects window's divider across the content row, separating the tabs from the open page
# (the user's request), a padding from each.
TAB_DIVIDER_TOP = TOGGLES_TOP + TOGGLE_SIZE + PADDING
PAGE_TOP = TAB_DIVIDER_TOP + DIVIDER_HEIGHT + PADDING  # where the pages' content starts
PAGE_TOP_GAP = PAGE_TOP - (TAB_ROW_HEIGHT - TAB_OVERLAP)  # the page border's Top height
ACTIONS_HEIGHT = 2 * BORDER + PAGE_TOP + ACTIONS_PAGE_HEIGHT + LEFT
ACTIONS_INSIDE_HEIGHT = ACTIONS_HEIGHT - 2 * BORDER
# Each template's pieces, all clear, as (width, height).
TAB_BORDER_PIECES = {
    'TopLeft': (TAB_CORNER, TAB_TOP), 'Top': (1, TAB_TOP), 'TopRight': (TAB_CORNER, TAB_TOP),
    'RightTop': (1, 1), 'Right': (1, 1), 'RightBottom': (1, 1),
    'LeftTop': (TAB_ICON_INSET, 1), 'Left': (TAB_ICON_INSET, 1), 'LeftBottom': (TAB_ICON_INSET, TAB_OVERLAP),
}
PAGE_BORDER_PIECES = {
    'TopLeft': (TAB_OFFSET, PAGE_TOP_GAP), 'Top': (1, PAGE_TOP_GAP), 'TopRight': (PAGE_RIGHT, PAGE_TOP_GAP),
    'RightTop': (PAGE_RIGHT, 1), 'Right': (PAGE_RIGHT, 1), 'RightBottom': (PAGE_RIGHT, 1),
    'BottomRight': (PAGE_RIGHT, LEFT), 'Bottom': (1, LEFT), 'BottomLeft': (LEFT, LEFT),
    'LeftTop': (LEFT, 1), 'Left': (LEFT, 1), 'LeftBottom': (LEFT, 1),
}
# Pages that open with a list with no heading (the friends window's) start higher, under a page border whose top row is
# that much shorter: the first name's ink a padding under the divider, as the tracking list's is under its dropdown.
LIST_PAGE_BORDER = 'TUI_ListPageBorder'
LIST_PAGE_TOP = TAB_DIVIDER_TOP + DIVIDER_HEIGHT + DIVIDER_TO_NAME
LIST_PAGE_BORDER_PIECES = {side: (width, height - (PAGE_TOP - LIST_PAGE_TOP) if side.startswith('Top') else height)
                           for side, (width, height) in PAGE_BORDER_PIECES.items()}
for _width in ACTION_WIDTHS:  # no label of ours: the button's text is the name
    BUTTON_LABELS[(_width, TEXT_BUTTON_HEIGHT)] = ('',)
# The Effects and Songs windows, as EQ Triage's tables: a row per slot, the spell's icon and then its
# name, a 1px divider between rows, compact (the user agreed this exception to the 6px rule). The client
# lays the slot buttons out itself, a pixel apart, so each runs across the row (one per row), and the
# dividers sit in the pixel between. The icon is a padding from the window's top and bottom. The client
# paints each slot with BlueIconBackground (helpful) or RedIconBackground (harmful), by name, so the skin
# redefines those two: clear for helpful effects, and a red bar on each side of the icon for harmful ones. The spellbook, item display and combat ability windows use them too and change with them (the
# user's call); the spell book lays its slots out so the red bars fall under its icons (see BOOK_ICON_X).
BUFF_FILE = 'EQUI_BuffWindow.xml'
SONG_FILE = 'EQUI_ShortDurationBuffWindow.xml'
BUFF_ICONS = 'BuffIcons'  # the stock spell icons the client puts on each slot
REPLACED_ANIMATIONS = ('BlueIconBackground', 'RedIconBackground', 'A_SpellBookSlot')  # the last, the spellbook's
ROW_ICON = 16
ROW_ICON_MARGIN = PADDING - BORDER
ROW_HEIGHT = ROW_ICON + 2 * ROW_ICON_MARGIN
ROW_PITCH = ROW_HEIGHT + 1
# Wider than the other windows' 200 so longer names fit: 159px for a name after Zeal's time column
# (TIMER_WIDTH), the icon and its harmful bars, where long bard songs run to about 167 in Arial 12. 220 at
# first (the user's call, 2026-09-26), then 12 more for a single bar after the icon (the user's pick,
# 2026-09-27, to keep the names' room) and the pixel the client's own slot placement takes (see SLOT_X).
# The user kept it when the two bars came ("the total width of the effect window should not change").
EFFECTS_WIDTH = 232
EFFECTS_RIGHT = EFFECTS_WIDTH - 2 * BORDER - LEFT
ROW_WIDTH = EFFECTS_WIDTH - 2 * BORDER
# The slot buttons are inset like the dividers, LEFT each side, so they're narrower than the window's inside.
# The client lays the slots out itself (skins with every slot at 0,0 or with no Location work), a pixel
# apart, and every working skin leaves room for that: duxaUI, poweroftwo and vert 4px (their slots at 3,3),
# WizModRyo 2px. Slots as wide as the inside (192 in 192) drew their art and Zeal's timers, but the client
# never hit-tested them: no tooltip on hover, no click, and no red for harmful effects, since the same slot
# refresh sets those (seen in game 2026-09-26, after four builds that changed the art and the draw order).
SLOT_WIDTH = ROW_WIDTH - 2 * LEFT
# Where the client puts each slot, whatever its Location: eqgame.exe lays them out (0x4090E9) from the
# inside's right, x = inside width - (slot width + 1), rows (slot height + 1) apart from y 0, in the same
# coordinates as Location (0x5751C0). So a pixel right of LEFT; the Location says where it lands.
SLOT_X = ROW_WIDTH - SLOT_WIDTH - 1
# Zeal's Buff Timers draws each effect's time left as a tooltip box pinned to its slot button's top left
# (ui_buff.cpp, BuffWindow_PostDraw), in its largest unit only ("2h", "18m", "45s"): the game's own tooltip
# (0x574800), the text's width + 4 by its font's height + 2, navy at alpha 200, in the slot's font (SIDL's
# default 3), so about 28x16 for "18m". It sat over the start of the names in game, so the row's marks start
# TIMER_WIDTH into the slot: 30px, the user's calls in game (36, then 24 left too much room before the names;
# at 18 and then 23 the box still covered some of the icons, so 5 more each time, to 28; then 30 on
# 2026-09-27, so the widest box keeps 2px from the harmful bar before the icon).
TIMER_WIDTH = 30
# A harmful effect's mark: a solid red bar HARMFUL_BAR_WIDTH wide on each side of its icon, touching it, as
# tall as the icon and level with it (the user's design, 2026-09-27: "one bar on the left and right of any
# detrimental effect", "the normal left padding, then a 3px red bar, then the spell icon, then another 3px
# red bar, then the prior normal padding to the start of the effect name text", then "increase the width of
# the bars by 1 px, total 4px width each" after a preview at 3). Helpful rows keep the room
# empty, so every icon and name starts at the same place. The client's art swap (0x409520: the slot's
# Normal is RedIconBackground when the spell's beneficial byte is 0) is the only sign of an effect's type a
# skin gets: the names (labels 45-59, 0x436F3D) are set without a color, so they can't turn red (Zeal's
# label hook could). The art is drawn from the slot's top left at its own size, so clear pixels put the bars
# in place. Before them: a faint red across the row, then a red square behind the icon at alpha 85, which
# left a 2px ring too faint to see, its left side under Zeal's timer box (the user had it removed), then a
# single 5px bar between the icon and the name.
HARMFUL_RGBA = (255, 68, 68, 255)
HARMFUL_BAR_WIDTH = 4
ROW_ICON_X = SLOT_X + TIMER_WIDTH + HARMFUL_BAR_WIDTH  # from the inside's left edge
HARMFUL_BARS = (ROW_ICON_X - HARMFUL_BAR_WIDTH, ROW_ICON_X + ROW_ICON)  # each bar's x, from the inside's left
ROW_NAME_X = ROW_ICON_X + ROW_ICON + HARMFUL_BAR_WIDTH + PADDING
# A helpful effect's row: clear, so the row is the panel at whatever alpha the window has. It was solid in
# the panel's color while clicks never reached the slots (the theory: a button ignores a click where its art
# is see-through), but the slots weren't hit-tested at all, being as wide as the inside (see SLOT_WIDTH),
# and once they were, the solid rows showed as darker stripes on rows with a buff at window Alpha 205 (the
# opaque row blends over the panel a second time). The theory stays unproven; if clicks stop with clear
# art, that's its one remaining case.
HELPFUL_RGBA = CLEAR
# The client looks up this many slot buttons (Buff0 to Buff14) in the Songs window as well as the Effects
# window (UIErrors.txt: could not find child Buff6 in window ShortDurationBuffWindow), so the slots a window
# doesn't show are hidden buttons.
CLIENT_SLOTS = 15
# The spell bar: duxaUI's spell gems (the user's pick) in the Effects window's table look, a row per gem with
# the gem's icon and then the spell's name, the whole row the gem so a click anywhere on it casts, rows a
# pixel apart with a divider between. Under each name, Zeal's countdown to that gem's recast as a thin bar
# like the other windows' (the user asked for it plain white, not subdued), and along the top Zeal's global
# recovery after a cast, the master timer over them all, in the casting window's soft red (the user's idea;
# the tracks' faint color at first, then white); under the rows, the spellbook's button as an icon
# toggle like the selector's, but across the window with the book in its middle: it gets clicked in a hurry,
# so the user asked for a bigger target. A divider closes the last gem's row too, and the book has a row of its
# own under it, for balance. No gem numbers (the user's calls). The client looks up only the eight gems and the
# book's button.
CASTSPELL_FILE = 'EQUI_CastSpellWnd.xml'
GEM_COUNT = 8
SPELL_BAR_WIDTH = 190  # narrower than the others (the user's call, after trying 195 and keeping 200 first)
SPELL_BAR_RIGHT = SPELL_BAR_WIDTH - 2 * BORDER - LEFT
SPELL_BAR_CONTENT_WIDTH = SPELL_BAR_RIGHT - LEFT
GEM_ROW_WIDTH = SPELL_BAR_WIDTH - 2 * BORDER  # the window's inside
# The client draws a gem's icon from A_SpellGems (24px cells), which the client names itself: the base skin's
# definition and textures, so EverQuest's own icons. It draws the gem's Holder and Background under the icon
# (duxaUI's Holder is opaque button art, and its icons show), so both are a row in
# the panel's color, solid so clicks land (see HELPFUL_RGBA). The rows are 32px, roomier than the Effects
# table's, so there's no room for error when casting (the user's calls: 28, then 36, a padding over and under
# each icon, a bit too large, then this).
GEM_ICON = 24
GEM_ICON_MARGIN = 4
GEM_ROW_HEIGHT = GEM_ICON + 2 * GEM_ICON_MARGIN
GEM_ROW_PITCH = GEM_ROW_HEIGHT + DIVIDER_HEIGHT
GEM_NAME_X = LEFT + GEM_ICON + PADDING
GEM_NAME_TOP = (GEM_ROW_HEIGHT - TEXT_HEIGHT) // 2
GEM_NAME_TYPE = 60  # the gems' spell names, labels 60 to 67 (the client's, as in duxaUI)
# Zeal's gauges 26 to 33, each gem's recast time left over its whole recast, and 25, the global recovery. Their
# own text (the seconds left, or 0) stays hidden.
RECAST_TYPE = 26
CAST_RECOVERY_TYPE = 25
RECAST_TOP = GEM_NAME_TOP + TEXT_HEIGHT + PET_BAR_GAP  # a pixel under the name's line, like a pet's bar
RECAST_WIDTH = SPELL_BAR_RIGHT - GEM_NAME_X
GEMS_TOP = TICK_HEIGHT + PADDING - GEM_ICON_MARGIN  # the first icon a padding under the global bar
# The book's toggle a padding under the divider that closes the last gem's row, from padding to padding across
# the window. Under it, a padding of clear pixels over the window's 1px edge line (EDGE_LINE), as over the
# divider: the usual padding to the window's outer edge counts the edge line, which left the gap under the book
# visibly smaller than the one above it (the user).
EDGE_LINE = 1
LAST_DIVIDER_TOP = GEMS_TOP + GEM_COUNT * GEM_ROW_PITCH - DIVIDER_HEIGHT
BOOK_TOP = LAST_DIVIDER_TOP + DIVIDER_HEIGHT + PADDING
BOOK_WIDTH = SPELL_BAR_CONTENT_WIDTH
SPELL_BAR_HEIGHT = 2 * BORDER + BOOK_TOP + TOGGLE_SIZE + LEFT + EDGE_LINE
# The hot button window, which the user calls the slot window: duxaUI's shape (the user's pick) in our look.
# On the left, the page arrows and page number over the ten macros, two to a row; on the right, the weapon
# slots (Primary and Secondary, Range and Ammo) over the bag slots, two columns of four. Every spot is a 36px
# square on one grid (the user's pick; duxaUI's macros were 36px and its slots 30px), so the rows line up across
# the window, a padding apart and from the window's edge (4px apart was tried in game; the user went back to the
# standard). The page row is a row tall: its arrows are the Actions window's chevrons, ARROW_SIZE wide. Each
# macro's spot also holds the client's item slot (EQType -1) and spell gem, which it shows for an item's or a
# spell's hot button. The game writes each macro's name,
# in font 1 as in duxaUI (the user's pick). An empty weapon slot shows a dimmed line icon of what goes there
# (the user's pick); an empty bag slot is the plain button, since anything goes there (a sack icon read as a
# ring in game). Everything is solid, the button look over the panel's color, since it's the window clicked
# most and the client seems to ignore clicks where a button's art is see-through (see HELPFUL_RGBA).
HOTBUTTON_FILE = 'EQUI_HotButtonWnd.xml'
# HOT_SIZE, HOT_COLUMNS and HOT_WIDTH are set before the pet window: the pet, group and Actions windows take its
# width.
HOT_PITCH = HOT_SIZE + BUTTON_GAP  # BUTTON_ROW_GAP down, the same
HOT_ROWS = 6
HOT_HEIGHT = 2 * PADDING + HOT_ROWS * HOT_SIZE + (HOT_ROWS - 1) * BUTTON_ROW_GAP
HOT_MACROS = 10  # two columns under the page row
MACRO_FONT = 1
# The right two columns, top to bottom: (EQType, the empty slot's icon, None for none). The bags go down each
# column, 1 to 4 then 5 to 8, as in duxaUI.
HOT_SLOTS = (
    ((13, 'Primary'), (11, 'Range'), *((22 + n, None) for n in range(4))),
    ((14, 'Secondary'), (21, 'Ammo'), *((26 + n, None) for n in range(4))),
)
# Their ScreenIDs are duxaUI's, down each column, its first capitalized as in duxaUI: right-clicks on items
# in these slots (opening a bag, using a clicky) stopped working in game with ScreenIDs of our own, where
# duxaUI's slots take them, so the slots copy duxaUI's XML in everything but place, size and art.
HOT_SLOT_IDS = ['NewSlot1'] + [f'Newslot{n}' for n in range(2, 13)]
HOT_ARROWS = (('HB_PageLeftButton', 'Previous Page', 'Left'), ('HB_PageRightButton', 'Next Page', 'Right'))
HOT_PAGE_LABEL = 'HB_CurrentPageLabel'
HOT_PAGE_WIDTH = 2 * HOT_SIZE + BUTTON_GAP  # the page row, over the two macro columns
HOT_PAGE_LABEL_TOP = round(HOT_SIZE / 2 - DIGITS_INK_MIDDLE)  # the digits' ink centered on the row
HOT_GEM_OFFSET = (HOT_SIZE - GEM_ICON) // 2  # a spell's 24px icon, centered on its spot
# The bag window, the one each open bag gets (Screen ContainerWindow): its slots the hot button window's 36px
# spots, two across as in duxaUI (four across didn't suit the user in game), and Done across the window under them,
# with Combine over it in a tradeskill container. No name: the bags don't need to show their own (the user). The game lays the window out itself
# whenever a bag opens (eqgame.exe, SetContainer at 0x41717D): it hides the slots past the bag's size, never
# moving one, shows Combine only in a tradeskill container, and measures a box around the label, the icon and the
# visible slots (a plain min/max union at 0x4176EC, so a control of no size still counts, as a point, and the box
# starts at the inside's corner if the label or the icon is missing). It moves Combine, then Done, BAG_BUTTON_GAP
# under the box, each growing it by its XML height, and sizes the window to the box plus BAG_EXTRA_WIDTH across
# and BAG_EXTRA_HEIGHT down (0x417633), whatever the XML's size.
CONTAINER_FILE = 'EQUI_Container.xml'
BAG_EXTRA_WIDTH = 14
BAG_EXTRA_HEIGHT = 36
BAG_BUTTON_GAP = 4
BAG_SLOTS = 10  # ContainerSlot1 to 10, EQTypes 30 to 39: the client looks up no more
BAG_SLOT_TYPE = 30
BAG_COLUMNS = 2
BAG_ROWS = -(-BAG_SLOTS // BAG_COLUMNS)
BAG_CONTENT_WIDTH = BAG_COLUMNS * HOT_SIZE + (BAG_COLUMNS - 1) * BUTTON_GAP
# Across, the game's 14px leave 7 each side of the grid (the user's pick over 6 and 8), an exception to the
# spacing standard. Down, the grid starts a padding from the window's top.
BAG_LEFT = (BAG_EXTRA_WIDTH - 2 * BORDER) // 2
BAG_WIDTH = BAG_CONTENT_WIDTH + BAG_EXTRA_WIDTH
BAG_TOP = LEFT
# The label and the icon, hidden, are the box's points at the grid's top corners, so every bag's window is the
# grid's width from the grid's top, however few its slots.
BAG_ICON_SPOT = (BAG_LEFT, BAG_TOP)
BAG_LABEL_SPOT = (BAG_LEFT + BAG_CONTENT_WIDTH, BAG_TOP)
# Down, the game's 36px would leave about 30 under Done. So Combine and Done are pinned to the window's bottom
# (AutoStretch): the client draws an anchored control where its anchors put it (GetLocation, 0x5750C0), wherever it
# moved it, but grows its box by the XML height, which the loader keeps apart from the anchors (0x59BC9C). Each
# button's XML height is its share of the window under the slots, less the gap the game adds anyway: Combine its
# own row; Done the padding over it, itself and the window's bottom padding, less the game's 36 (so it's negative).
BAG_DONE_BOTTOM = LEFT  # up from the inside's bottom, a padding from the window's edge
BAG_COMBINE_BOTTOM = BAG_DONE_BOTTOM + BUTTON_HEIGHT + BUTTON_ROW_GAP
BAG_COMBINE_LAYOUT_HEIGHT = BUTTON_ROW_GAP + BUTTON_HEIGHT - BAG_BUTTON_GAP
BAG_DONE_LAYOUT_HEIGHT = (BAG_TOP + PADDING + BUTTON_HEIGHT + BAG_DONE_BOTTOM + 2 * BORDER - BAG_BUTTON_GAP
                          - BAG_EXTRA_HEIGHT)
# (ScreenID, label, bottom offset, XML height), in the stock order.
BAG_BUTTONS = (('Container_Combine', 'Combine', BAG_COMBINE_BOTTOM, BAG_COMBINE_LAYOUT_HEIGHT),
               ('DoneButton', 'Done', BAG_DONE_BOTTOM, BAG_DONE_LAYOUT_HEIGHT))
_size = (BAG_CONTENT_WIDTH, BUTTON_HEIGHT)  # the group window's buttons' size too
BUTTON_LABELS[_size] = BUTTON_LABELS.get(_size, ()) + tuple(label for _, label, _, _ in BAG_BUTTONS)
# The XML size is a 10-slot bag's; the game sets its own.
BAG_HEIGHT = (2 * BORDER + BAG_TOP + BAG_ROWS * HOT_SIZE + (BAG_ROWS - 1) * BUTTON_ROW_GAP + PADDING + BUTTON_HEIGHT
              + BAG_DONE_BOTTOM)
# The Player window, trimmed to what the user wants, in the layout the user gave: "Health" and its
# "current/max" (label 70) on a line, the HP bar under it as in the group window, the same for
# "Mana" (Zeal's label 80, its numbers green, its bar a soft blue), a line with your XP and AA rates, then the
# resists as a small table, a caption over each number, abbreviated as the user prefers. Health and Mana
# show your % (labels 19 and 20) in the middle of their line. Each section starts two paddings under the
# bar above, measured to the caption's ink. The client looks up its four gauges; stamina and pet stay,
# hidden.
PLAYER_FILE = 'EQUI_PlayerWindow.xml'
# As wide as the hot button and actions windows (the user's requests: 200, 180, 162, the pet's 177, then this).
PLAYER_WIDTH = HOT_WIDTH
PLAYER_RIGHT = PLAYER_WIDTH - 2 * BORDER - LEFT
PLAYER_CONTENT_WIDTH = PLAYER_RIGHT - LEFT
# Health at the top, like the other windows' first lines. No line with your name (the user's request, to save it).
PLAYER_SECTIONS_TOP = 0
# Two paddings from a bar to the next caption's ink, as from XP/hour to the resists: the user asked for the
# sections set apart, less cluttered.
PLAYER_SECTION_PITCH = BAR_TOP + BAR_HEIGHT + math.ceil(2 * PADDING - PERCENT_INK_TOP - PERCENT_SUBPIXEL)
# The server tick in the mana section, TICK_GAP under its bar (see TICK_TYPE).
MANA_TICK_TOP = BAR_TOP + BAR_HEIGHT + TICK_GAP
# The health bar: '#8fd19e', the soft green the current HP number had at first (the user's pick).
HP_RGB = (143, 209, 158)
# The values: the current number, "/" and the max, as separate labels (the current right-aligned against
# the slash, the max left-aligned after it in a spot for 4 digits), the health and mana %, the XP and AA rates and
# the resists' values, each % drawn in the same color. Every one is the green the game gives a value above its base
# (0xff00ff00). The game colors max HP (label 18) and the resists (12 to 16) itself, whatever a skin sets, and no
# skin can stop it: this green while buffs or gear raise them, grey (0xffc0c0c0) at their base, red below it. The
# rest stay this green, so they match raised stats (the user's pick over the game's grey; a softer green, white, and
# the percentages in gold were tried). The slash is in the text color (the user's request).
VALUE_RGB = (0, 255, 0)
# The inventory's XP and AA percentages, with their drawn %s and bars, in EverQuest's classic golden yellow (the
# user's request).
GOLD_RGB = (230, 184, 46)
PLAYER_NUMBER_WIDTH = 28  # "8888" in font 3 (Arial 12px)
SPACE_WIDTH = 3  # a space in font 3 (Arial 12px)
DIGIT_WIDTH = 7  # a digit in font 3 (Arial 12px; "100" is NUMBER_WIDTH)
# The slash (4px) with a space either side, so the numbers read apart (the user's request).
PLAYER_SLASH_WIDTH = 4 + 2 * SPACE_WIDTH
RESISTS = (('DR', 13), ('PR', 12), ('MR', 16), ('FR', 14), ('CR', 15))  # (caption, label EQType)
CAPTION_FONT = 2
CAPTION_HEIGHT = 12
# The captions (Health, Mana and the resists) in the text's color: the user didn't like them in the overlay's
# subdued grey.
CAPTION_RGB = TEXT_RGB
# XP/hour (the user's request), on its own line under the mana bar like a section with no bar (the user's pick
# from a mockup), two paddings under its tick like the sections: Zeal's label 81, the percent of a level you gain an
# hour, a whole number from 0 to 600, averaged over up to the last two hours (/resetexp and /load start it
# over), with the drawn % after it. It counts regular XP only, so it stays 0 with AA at 100% (the user's
# "doesn't seem to be working"), and Zeal's label 86, the percent of an AA point an hour, shares the line
# (the user's pick).
XP_PER_HOUR_TYPE = 81
AA_PER_HOUR_TYPE = 86
# Each rate is a pair: its caption, a padding, then its number (right-aligned in room for "100") and drawn %,
# "XP/h" at the line's start and "AA/h" ending at its end. Lined up with the columns above, XP's value sat
# nearer "AA/h" than its own caption (the user: "spacing is weird"). With fewer digits the gap after the
# caption grows a digit's width each, since the number hugs its %.
RATE_CAPTION_WIDTH = 26  # "XP/h" and "AA/h" in font 3 (Arial 12px)
RATE_PAIR_WIDTH = RATE_CAPTION_WIDTH + PADDING + NUMBER_WIDTH + PERCENT_WIDTH
PLAYER_XP_TOP = PLAYER_SECTIONS_TOP + 2 * PLAYER_SECTION_PITCH + TICK_GAP + TICK_HEIGHT  # under the tick
# The resists a padding further down than the rule's (the user's request), under the XP/hour line's ink.
RESISTS_TOP = PLAYER_XP_TOP + PERCENT_INK_TOP + PERCENT_GLYPH_HEIGHT + 2 * PADDING - CAPTION_INK_TOP
# Under the resists' numbers, whose ink ends where the drawn %'s does, the window's edge a padding away.
PLAYER_BOTTOM_GAP = PADDING - BORDER - (TEXT_HEIGHT - PERCENT_INK_TOP - PERCENT_GLYPH_HEIGHT)
ROW_DIVIDER_RGBA = (255, 255, 255, 34)  # softer than the bars' track, at the user's request
# The chat windows: no title bar (the user: everyone knows which window they chat in), the chat on the
# panel with the usual padding, and the input line along the bottom on a plain strip (the user wanted
# it simple), darker than the panel rather than lighter: a near-black navy half over it, outlined by a
# 1px line in the window edge's color. The client makes every chat window from this one template and
# remembers each one's size.
FIELD_RGBA = (0, 0, STEP, 7 * STEP)  # on the steps; the panel's color at half brightness isn't
CHAT_SIZE = (421, 200)  # the default skin's, for a window the client has no size for yet
INPUT_HEIGHT = 20  # 18 cut off the bottom of letters in game
INPUT_GAP = 3
# The scrollbar: SCROLL_WIDTH wide like the stock one, with clear track, a thin rounded thumb and small
# chevron arrows in soft white, brighter when hovered or pressed.
SCROLL_WIDTH = 12
SCROLL_BUTTON_HEIGHT = 10
SCROLL_LOOKS = {'Normal': 102, 'Flyby': 170, 'Pressed': 238, 'Disabled': 51}  # alphas, on the steps
THUMB_WIDTH = 4
THUMB_CAP = 3  # the rounded top and bottom pieces' height
THUMB_ALPHA = 85
# A chat window is sizable, and in this client a sizable window with no title bar can't be dragged at
# all, only resized edge by edge (poweroftwo's readme says so of its own title-less chat window; the
# other TriageUI windows drag by their background because they aren't sizable). A grab spot of the
# window's own background in the bottom right corner, marked with six dots, never moved the window in
# game. So each chat window has a really thin title bar (the user's call): TITLE_HEIGHT tall, in the
# panel's color with a row divider along its bottom to show where to drag, drawn by the chat frame
# template's own title pieces (the stock rounded title pieces are opaque rectangles, so the client draws
# a title bar inside the border, under the top edge). The client names each chat window and writes the
# name on the bar in its own color: neither a TextColor of the panel's color nor one with an alpha of 0
# hid it in game, and no skin setting can (the client sets the name after making the window). So the name
# stays, in the window's Font, TITLE_FONT: the user asked for 2 after the smallest, 0. The bar's height
# went 8 (a medium-sized header to the user in game), 3, 6, back to 8 for the font, then 2px taller, at the
# user's requests.
TITLE_HEIGHT = 10
TITLE_FONT = 2
TITLE_PIECE_WIDTH = PIECE_LENGTH
CHAT_TEMPLATE = 'WDT_TriageChat'
# The input box has no padding setting, so a strip piece draws the field and the see-through input box
# sits on it, inset FIELD_PADDING each side: the text starts about as far in as it sits from the top.
FIELD_PADDING = 4
# The raid window, in the shape the user picked: a fixed size like the other windows, so it drags by its
# background (a sizable one would need a title bar to drag). The client fills two lists, the raid's players in a
# group and those in none, straight on the panel with our slim scrollbar, each column's heading on a strip of the
# overlay's header tint. A caption names the second list. Under them the buttons, two rows of three, the client
# showing Accept and Decline in Invite's and Disband's spots during an invitation, as in the group window. The
# user wanted every button, no level column, and no player count or level average. The client looks up every
# control by ScreenID (eqgame.exe's string table lists them all but the stock skin's two static labels, which
# stay too, hidden, like every control the stock window has).
RAID_FILE = 'EQUI_RaidWindow.xml'
# The client's five columns, in its order: (heading, width). Each is its widest text in font 3 (Arial 12px) and a
# padding: "Grp" 20px, "Shadow Knight" 83, "Group Leader" 76 (the client's ranks are Raid Leader and Group
# Leader). Names get the stock skin's 85, about 13 letters. The level column has no width and no heading.
RAID_COLUMNS = (('Grp', 26), ('Name', 85), ('', 0), ('Class', 89), ('Rank', 82))
RAID_LIST_WIDTH = sum(width for _, width in RAID_COLUMNS) + SCROLL_WIDTH
RAID_WIDTH = RAID_LIST_WIDTH + 2 * PADDING
# A list is its heading row, the stock header pieces' height (the client's own for it is unknown), and its rows,
# estimated at font 3's line: about 16 in the grouped list and 4 in the other, which puts the window near the
# height the user had given the old one (392).
RAID_HEADER_HEIGHT = 16
RAID_GROUPED_ROWS = 16
RAID_UNGROUPED_ROWS = 4
RAID_GROUPED_HEIGHT = RAID_HEADER_HEIGHT + RAID_GROUPED_ROWS * TEXT_HEIGHT
RAID_UNGROUPED_HEIGHT = RAID_HEADER_HEIGHT + RAID_UNGROUPED_ROWS * TEXT_HEIGHT
# The caption's ink a padding under the grouped list, and the second list a padding under the caption's ink
# bottom (level with the digits' bottom, as the pet window's buttons are measured).
RAID_CAPTION_TOP = LEFT + RAID_GROUPED_HEIGHT + DIVIDER_TO_NAME
RAID_UNGROUPED_TOP = RAID_CAPTION_TOP + PERCENT_INK_TOP + PERCENT_GLYPH_HEIGHT + PADDING
RAID_BUTTONS_TOP = RAID_UNGROUPED_TOP + RAID_UNGROUPED_HEIGHT + BUTTON_ROW_GAP
# The buttons: (ScreenID, label, tooltip, column, row), the stock skin's tooltips (Decline's typo fixed). The three
# columns fill the lists' width, a padding apart.
RAID_BUTTONS = (
    ('Raid_InviteButton', 'Invite', 'Select a player and click to invite into the raid', 0, 0),
    ('Raid_AcceptButton', 'Accept', 'Accept an invitation to raid', 0, 0),
    ('Raid_DisbandButton', 'Disband', 'Click to disband your target from the raid', 1, 0),
    ('Raid_DeclineButton', 'Decline', 'Refuse an invitation to raid', 1, 0),
    ('Raid_MakeLeaderButton', 'Make Leader', 'Assign Raid Leadership', 2, 0),
    ('Raid_AddLooterButton', 'Add Looter', 'Add a raid member as a looter', 0, 1),
    ('Raid_RemoveLooterButton', 'Remove Looter', 'Remove a raid looter', 1, 1),
    ('Raid_OptionsButton', 'Options', 'Bring up options window', 2, 1),
)
RAID_BUTTON_COLUMNS = 3
RAID_BUTTON_ROWS = 2
_RAID_SPAN = RAID_LIST_WIDTH - (RAID_BUTTON_COLUMNS - 1) * BUTTON_GAP
RAID_BUTTON_WIDTHS = tuple(_RAID_SPAN * (c + 1) // RAID_BUTTON_COLUMNS - _RAID_SPAN * c // RAID_BUTTON_COLUMNS
                           for c in range(RAID_BUTTON_COLUMNS))
for _screen_id, _label, _tooltip, _column, _row in RAID_BUTTONS:
    _size = (RAID_BUTTON_WIDTHS[_column], BUTTON_HEIGHT)
    BUTTON_LABELS[_size] = BUTTON_LABELS.get(_size, ()) + (_label,)
RAID_HEIGHT = (2 * BORDER + RAID_BUTTONS_TOP + RAID_BUTTON_ROWS * BUTTON_HEIGHT + (RAID_BUTTON_ROWS - 1) * BUTTON_ROW_GAP
               + BOTTOM_GAP)
# The first list's caption and the player count and level average, with their static texts, hidden.
RAID_HIDDEN_LABELS = ('RAID_PlayerListLabel', 'RAID_PlayerCountLabel', 'RAID_PlayerCountStringLabel',
                      'RAID_LevelAverageLabel', 'RAID_LevelAverageStringLabel')
# A list column's heading strip: the overlay's header tint (EQ Triage's HEADER_COLOR, white at 20), on the steps
# as the buttons' wash. One flat piece serves as the header's left, middle and right, which the client repeats
# like the stock Header_Listbox's.
LIST_HEADER = 'TUI_ListHeader'
HEADER_RGBA = BUTTON_STYLES['Wash'][0]
# The merchant window, in the shape the user picked (2026-09-27): all 80 of a merchant's slots at once, eight
# across on the hot button window's 36px squares (duxaUI's shape, so nothing scrolls), empty ones the plain square;
# under them the item you're considering, with Project Quarm's recharge group beside it, then Buy or Sell and Done.
# No merchant name (the user). The client looks up the name (hidden here), the slots' panel and its 80 slots, the
# item's square, Buy, Sell and Done (the ScreenID DoneButton), and shows Buy for the merchant's items and Sell for
# yours in one spot; the price of what you consider comes in chat. Quarm's eqgame.dll (its 2026 recharge) looks up
# four more (see MERCHANT_RECHARGE).
MERCHANT_FILE = 'EQUI_MerchantWnd.xml'
MERCHANT_SLOTS = 80  # MW_MerchantSlot0 to 79, EQTypes 6000 to 6079
MERCHANT_SLOT_TYPE = 6000
MERCHANT_COLUMNS = 8
MERCHANT_ROWS = -(-MERCHANT_SLOTS // MERCHANT_COLUMNS)
MERCHANT_CONTENT_WIDTH = MERCHANT_COLUMNS * HOT_SIZE + (MERCHANT_COLUMNS - 1) * BUTTON_GAP
MERCHANT_WIDTH = MERCHANT_CONTENT_WIDTH + 2 * PADDING
MERCHANT_RIGHT = MERCHANT_WIDTH - 2 * BORDER - LEFT
MERCHANT_GRID_HEIGHT = MERCHANT_ROWS * HOT_SIZE + (MERCHANT_ROWS - 1) * BUTTON_ROW_GAP
# The stock item icons, which the client puts on the considered item's square (like BUFF_ICONS on the effects').
ITEM_ICONS = 'A_DragItem'
# Under the grid, a band a square tall: the considered item's square, then a column of text a padding after it, then
# the Recharge button over Done's column, a padding from the text. Quarm's eqgame.dll swaps what shows there: while
# one of your own items with charges is selected, its charges and the next charge's price (one line each, which it
# writes) and the Recharge button, whose tooltip it overwrites with the price per charge; otherwise
# MW_SelectedItemLabel, which it never writes and which says nothing here (the user). It moves nothing: its one layout
# change, the slots' panel's bottom anchor, has no effect on a panel placed by Location and Size.
# Between the grid and the band, the row divider across the content row, a padding from each (the user's request,
# to set the considered item apart from the slots).
MERCHANT_DIVIDER_TOP = LEFT + MERCHANT_GRID_HEIGHT + PADDING
MERCHANT_BAND_TOP = MERCHANT_DIVIDER_TOP + DIVIDER_HEIGHT + PADDING
MERCHANT_BUTTON_WIDTHS = ((MERCHANT_CONTENT_WIDTH - BUTTON_GAP) // 2,
                          MERCHANT_CONTENT_WIDTH - BUTTON_GAP - (MERCHANT_CONTENT_WIDTH - BUTTON_GAP) // 2)
MERCHANT_RECHARGE_X = MERCHANT_RIGHT - MERCHANT_BUTTON_WIDTHS[1]  # over Done
MERCHANT_TEXT_X = LEFT + HOT_SIZE + PADDING
MERCHANT_TEXT_WIDTH = MERCHANT_RECHARGE_X - PADDING - MERCHANT_TEXT_X
# The two lines stacked on their line height, the ink of both (the first's top to the second's digits' bottom)
# centered on the square, as the page numbers' digits are on their arrows.
MERCHANT_TEXT_TOP = round(HOT_SIZE / 2 - (TEXT_HEIGHT / 2 + DIGITS_INK_MIDDLE))
MERCHANT_RECHARGE_TOP = (HOT_SIZE - TEXT_BUTTON_HEIGHT) // 2  # the button centered on the square
# The recharge group, as (ScreenID, line): the item label covers both lines.
MERCHANT_RECHARGE = (('MW_Recharge_Charges', 0), ('MW_Recharge_Price', 1))
MERCHANT_ITEM_LABEL = 'MW_SelectedItemLabel'
MERCHANT_RECHARGE_BUTTON = 'MW_Recharge_Button'
# Buy and Sell share a spot, a padding under the band, and Done has the other half of the row: (ScreenID, name,
# tooltip, column), the client's own tooltips. Done has none. Every button here, Recharge too, is the confirmation
# dialog's kind (the user's pick), its name its own text.
MERCHANT_BUTTONS_TOP = MERCHANT_BAND_TOP + HOT_SIZE + BUTTON_ROW_GAP
MERCHANT_BUTTONS = (('MW_Buy_Button', 'Buy', 'Purchase considered item', 0),
                    ('MW_Sell_Button', 'Sell', 'Sell considered item', 0),
                    ('DoneButton', 'Done', None, 1))
add_text_buttons(MERCHANT_BUTTON_WIDTHS)
MERCHANT_HEIGHT = 2 * BORDER + MERCHANT_BUTTONS_TOP + TEXT_BUTTON_HEIGHT + BOTTOM_GAP
# The confirmation dialog: the box that asks before a resurrection, looting a NODROP item, destroying an item or a
# translocation (Yes and No), or shows a notice (OK alone; the client never shows all three). The client looks up
# the text (TextOutput) and the three buttons; default's static Text1 is in no skin's window and not in eqgame.exe,
# so it's left out. The game never resizes the box, and centers it when it shows it (unless Zeal's DialogPosition
# option keeps it where it was); Zeal draws a timed question's time left at its top right corner. The user's picks
# (2026-09-27, from mockups): the window selector's width with room for three lines, where every common message
# (about 45 to 100 characters, eqstr_en.txt) takes two and the Sacrifice warning three; Yes and No filling the row,
# OK alone in the middle at their width. Then, since "confirmation boxes are important" (the user, the same day):
# the Actions window's buttons, taller and with their names in the game's font 2, and more room inside
# (DIALOG_PADDING). A red edge came with them and went again at the user's request.
CONFIRM_FILE = 'EQUI_ConfirmationDialog.xml'
# Dialogs, windows with only text and buttons, keep two paddings from their edge to what's inside and between the
# text and the buttons (the user asked for "better spacing for these type of dialog boxes" and picked 12 from
# mockups); buttons side by side stay BUTTON_GAP apart. DIALOG_LEFT is that padding inside the frame.
DIALOG_PADDING = 2 * PADDING
DIALOG_LEFT = DIALOG_PADDING - BORDER
CONFIRM_WIDTH = SELECTOR_WIDTH
CONFIRM_RIGHT = CONFIRM_WIDTH - 2 * BORDER - DIALOG_LEFT
CONFIRM_CONTENT_WIDTH = CONFIRM_RIGHT - DIALOG_LEFT
CONFIRM_TEXT_LINES = 3
# The first line's ink a dialog padding under the window's edge (rounded up to a whole pixel, so at least that far),
# and the buttons a dialog padding under the last line's digits (the pet window's measure under its health).
CONFIRM_TEXT_TOP = math.ceil(DIALOG_PADDING - BORDER - TEXT_INK_TOP)
CONFIRM_BUTTONS_TOP = (CONFIRM_TEXT_TOP + (CONFIRM_TEXT_LINES - 1) * TEXT_HEIGHT + PERCENT_INK_TOP
                       + PERCENT_GLYPH_HEIGHT + DIALOG_PADDING)
CONFIRM_BUTTON_WIDTHS = ((CONFIRM_CONTENT_WIDTH - BUTTON_GAP) // 2,
                         CONFIRM_CONTENT_WIDTH - BUTTON_GAP - (CONFIRM_CONTENT_WIDTH - BUTTON_GAP) // 2)
CONFIRM_OK_X = DIALOG_LEFT + (CONFIRM_CONTENT_WIDTH - CONFIRM_BUTTON_WIDTHS[0]) // 2
# (ScreenID, name, x, width): the stock skin's buttons have no tooltips.
CONFIRM_BUTTONS = (('Yes_Button', 'Yes', DIALOG_LEFT, CONFIRM_BUTTON_WIDTHS[0]),
                   ('No_Button', 'No', DIALOG_LEFT + CONFIRM_BUTTON_WIDTHS[0] + BUTTON_GAP, CONFIRM_BUTTON_WIDTHS[1]),
                   ('OK_Button', 'OK', CONFIRM_OK_X, CONFIRM_BUTTON_WIDTHS[0]))
for _width in sorted(set(CONFIRM_BUTTON_WIDTHS)):  # no label of ours: the button's text is the name
    _size = (_width, TEXT_BUTTON_HEIGHT)
    BUTTON_LABELS[_size] = BUTTON_LABELS.get(_size, ()) + ('',)
CONFIRM_HEIGHT = 2 * BORDER + CONFIRM_BUTTONS_TOP + TEXT_BUTTON_HEIGHT + DIALOG_LEFT
# The item window: what the game shows when you right-click an item, or a spell with Zeal's spell info on. From
# eqgame.exe: it looks up only ItemDescription (the text) and IconButton (0x423331). SetItem (0x423640) writes the
# item's name into the window's title alone (the text never has it), builds the text, and makes the item's icon, an
# A_DragItem cell 40px square, the icon button's own Normal art, clearing its decal. SetSpell puts the spell's
# A_SpellIcons cell (40px too) in the decal and has the buff window paint the button BlueIconBackground or
# RedIconBackground, the effect slots' art. Neither moves nor resizes anything. The window handles one click, on the
# icon, which puts a link to the item in the chat input (0x425cf6), and Page Up and Page Down scroll the text
# (0x425d69). Zeal makes its own item windows (ZealItemDisplay0 to 4 in the character's ini) from the same XML, links
# only ItemDescription and then IconButton as their children, and keeps no size for them, so they open at the XML's.
# The user's picks (2026-09-27, from mockups): a title bar with the name in font 3, the icon at the top left with
# the text in a column to its right, a Close button on the bar (the close box: the game handles no other button here,
# so none inside the window could close it), and a fixed size. Close is the dialogs' kind of button (2026-09-29, the
# user's pick), the quantity window's Accept's size with its name in font 2's look (see CLOSE_INK).
ITEM_FILE = 'EQUI_ItemDisplay.xml'
ITEM_TEMPLATE = 'WDT_TriageItem'
ITEM_WIDTH = 400  # the stock window's
ITEM_RIGHT = ITEM_WIDTH - 2 * BORDER - LEFT
ITEM_ICON = 40  # the game's item and spell icons, drawn at their own size
ITEM_TEXT_X = LEFT + ITEM_ICON + PADDING
# The first line's ink level with the icon's top, a padding under the title bar, if the text box draws its first
# line at its top like a label.
ITEM_TEXT_TOP = PADDING - PERCENT_INK_TOP
ITEM_TEXT_LINES = 12
# The close box, from eqgame.exe (0x57165a): drawn at its art's size, its right edge CLOSE_BOX_INSET in from the
# inside's right edge (the window within its border) and its top CLOSE_BOX_TOP under the title bar's. A minimize box
# would sit at the bar's left, 8 in and 2 down. The bar is as tall as its pieces, and the game writes the window's
# title on it in the window's Font, centered across the bar and down it less a pixel, light grey (#c0c0c0), white
# while the window is active (0x5729b0). So the Close button's right edge is 11px from the window's (the user
# accepted it, forced), and a narrow window's title runs under it (see QUANTITY_TITLE_INK).
CLOSE_BOX_TOP = 1
CLOSE_BOX_INSET = 7
CLOSE_WIDTH = 72  # the quantity window's Accept's, which it sits over there
# Clear rows over the Close button in its art, so it starts a padding under the window's top edge. More would center
# it on the name (about 2px lower, by the game's rule and an estimate of font 3's height), at the padding's cost.
CLOSE_CLEAR = PADDING - BORDER - CLOSE_BOX_TOP
# The Close button's name. The game draws a close box's art and writes nothing on it, so the name is painted into
# the art in font 2's look, like the text the game writes on Accept: the ink's coverage as tools/preview.py draws font 2
# (Arial 10px) on a button Close's size, a hex digit a pixel (0 to f, the 16 alpha steps), CLOSE_INK_AT from the
# button's top left. A test draws it again. If it differs from Accept's name in game, copy the game's letters from a
# lossless screenshot instead.
CLOSE_INK_AT = (23, 7)
CLOSE_INK = (
    '02bee805800000000000000000',
    '1d612b65800000000000000000',
    '6a00012580aed402cfc209ed30',
    '7800000587a13d17a2006913d0',
    '5a00025589400b22bfd39ffff1',
    '1d612b7587a13e100188791000',
    '03cee80581aed505dfc20aee90',
)
# The chat windows' close box: an X (the user's pick: their bar is too thin for a Close button) in the soft white of
# their scrollbar's arrows, brighter when hovered or pressed (SCROLL_LOOKS). The game places it like Close, so it is a
# square as far above the divider as its top is under the bar's top, the X in its middle: centered down the bar above
# the divider. The game clicks it only within its art, this small.
CHAT_CLOSE_SIZE = TITLE_HEIGHT - DIVIDER_HEIGHT - 2 * CLOSE_BOX_TOP
CHAT_CLOSE_REACH = 2.5  # the X's arms, each way from its middle: the arrows' width
# The bar: the Close button, a padding under it, then the divider as the bar's bottom row.
ITEM_TITLE_HEIGHT = CLOSE_BOX_TOP + CLOSE_CLEAR + TEXT_BUTTON_HEIGHT + PADDING + DIVIDER_HEIGHT
ITEM_HEIGHT = 2 * BORDER + ITEM_TITLE_HEIGHT + ITEM_TEXT_TOP + ITEM_TEXT_LINES * TEXT_HEIGHT + LEFT
# The quantity window: what the game asks with when you pick up part of a stack or of your coins. From eqgame.exe
# (CQuantityWnd, 0x42F1A0): it looks up the slider, the number field and Accept, nothing else, and uses the first two
# unchecked, so both must be there. Each time it opens it sets the slider from 0 to the stack's size and the number
# to the whole stack, puts the window's top left on the middle of the slot you clicked (kept on the screen at the
# right and bottom), and leaves the caret after the number, so what you type is added to it. The field takes only
# digits and caps the number at the stack; Enter or Accept takes it. It never moves or resizes anything inside. The
# user's picks (2026-09-28, from mockups): the stock arrangement, the slider across the window over the field and
# Accept side by side; the slider a knob on the bars' faint track; a dialog's room inside (DIALOG_PADDING). As wide as
# the hot button window, like the other small windows. The item window's title bar with its Close (2026-09-29, the
# user's pick): the close box is the only button the game lets close it; Esc closes it too.
QUANTITY_FILE = 'EQUI_QuantityWnd.xml'
QUANTITY_WIDTH = HOT_WIDTH
QUANTITY_RIGHT = QUANTITY_WIDTH - 2 * BORDER - DIALOG_LEFT
QUANTITY_CONTENT_WIDTH = QUANTITY_RIGHT - DIALOG_LEFT
# The slider, from eqgame.exe (CSliderWnd, 0x5A69D0): its template's background is stretched between the end caps,
# which sit at the slider's left and right edges at their own size, all three centered down the slider by the
# background's height. The knob (Thumb, drawn at its Normal art's size) has its top level with the background's, and
# its left edge goes from the left cap's width (at 0) to the slider's width less the right cap's (at the most). So the
# left cap has no width and the right cap is as wide as the knob, which just fits at either end, and the background
# is the rest of the slider, so it's drawn at its own size. All three are as tall as the knob, with the track's line
# across their middle. A click on the track, or a drag, puts the knob's left edge at the pointer.
SLIDER_TEMPLATE = 'TUI_Slider'
SLIDER_KNOB_WIDTH = 10
SLIDER_HEIGHT = 15  # the knob's, odd so the 3px track centers on it
SLIDER_TRACK_TOP = (SLIDER_HEIGHT - TWIN_BAR_HEIGHT) // 2
# The knob a dialog padding under the title bar's line, the bar's bottom row, where the controls' inside starts.
QUANTITY_SLIDER_TOP = DIALOG_PADDING
# The number field (the chat input's strip) and Accept (the confirmation dialog's buttons) share the row a dialog
# padding under the knob, each half of it. Close, over Accept, sits a pixel further right: the game's inset.
QUANTITY_ROW_TOP = QUANTITY_SLIDER_TOP + SLIDER_HEIGHT + DIALOG_PADDING
QUANTITY_ROW_WIDTHS = ((QUANTITY_CONTENT_WIDTH - BUTTON_GAP) // 2,
                       QUANTITY_CONTENT_WIDTH - BUTTON_GAP - (QUANTITY_CONTENT_WIDTH - BUTTON_GAP) // 2)
QUANTITY_ACCEPT_X = QUANTITY_RIGHT - QUANTITY_ROW_WIDTHS[1]
_size = (QUANTITY_ROW_WIDTHS[1], TEXT_BUTTON_HEIGHT)  # no label of ours: the button's text is its name
BUTTON_LABELS[_size] = BUTTON_LABELS.get(_size, ()) + ('',)
QUANTITY_HEIGHT = 2 * BORDER + ITEM_TITLE_HEIGHT + QUANTITY_ROW_TOP + TEXT_BUTTON_HEIGHT + DIALOG_LEFT
# The window's name. The game would center it across the bar, under Close in a window this narrow, so the window has
# no title for it to write and its name is painted into the bar's left piece instead (QUANTITY_TEMPLATE), in the text's
# color: the ink's coverage as tools/preview.py draws font 3 (see CLOSE_INK), its top left QUANTITY_TITLE_INK_AT in the
# bar. That puts the ink a dialog padding from the window's left and top edges, level with the slider's left edge,
# and its capitals (all but the y's two rows of tail) share Close's name's middle.
QUANTITY_TEMPLATE = 'WDT_TriageQuantity'
QUANTITY_TITLE_INK_AT = (DIALOG_LEFT, DIALOG_PADDING - BORDER)
QUANTITY_TITLE_INK = (
    '006cfd8100000000000000000000000d03d00d0000000',
    '08d412bb00000000000000000000000f00000f0000000',
    '1f30000d54c004c007dfd403caec30cff4d0cffa7005b',
    '6c00000894c004c03d219b03f619b00f03d00f04c0096',
    '7b000007b4c004c000004c03e003d00f03d00f00d20d1',
    '6c00000994c004c0049bec03d003d00f03d00f00873b0',
    '1f30271d53d005c05d645c03d003d00f03d00f002c860',
    '07d42cec01f41cc08b12cd03d003d00f23d00f200ce10',
    '006cfd6c807ed6c02cec5f13d003d00af5d00af208b00',
    '00000001400000000000000000000000000000001d500',
    '0000000000000000000000000000000000000004e9000',
)
# Coin boxes (the give and trade windows, see coin_box()): the buttons the game writes an amount of one coin on, as
# its text, centered, in font 3. Money0 to 3 are platinum, gold, silver and copper in every window, as the stock
# windows' coin decals show. Each box is the slots' wash with its coin's name a padding in from its left edge (the
# user's pick, over the stock coin pictures), as tall as the quantity window's number field and as wide as two slots
# and the padding between them. The name is a label over the box in the amount's font 3 (the user's pick, the
# windows' normal text; in the buttons' font 2 on the amount's baseline it read small and low): the box's own text is
# the amount. Labels let clicks through (see the Actions window's tabs), so a drop on it counts.
COIN_CAPTIONS = ('pp', 'gp', 'sp', 'cp')
COIN_WIDTH = 2 * HOT_SIZE + BUTTON_GAP
COIN_HEIGHT = TEXT_BUTTON_HEIGHT
COIN_TOOLTIP = 'Drop coins here'  # the stock windows', on your own coins
# The name's ink level with the amount's digits, top and bottom: the game centers the amount's line in the box, so its
# digits' ink runs from TEXT_INK_TOP down that line for 9px. The names are lowercase with a descender (p, g), 9px of
# ink too, from the x-height, LOWERCASE_DROP under the digits' top, to the descenders, as far under their bottom. On
# the amount's line, the names sat that much low.
LOWERCASE_DROP = 2  # font 3 (Arial 12px)
COIN_TEXT_TOP = (COIN_HEIGHT - TEXT_HEIGHT) // 2
COIN_CAPTION_TOP = COIN_TEXT_TOP - LOWERCASE_DROP
# "pp" and "gp" are the widest, 14px in Arial 12px. Five digits of an amount (the stock windows' placeholder is
# 60000), centered, start where the label ends; six would reach the name.
COIN_CAPTION_WIDTH = 14
# The give window: what opens when you hand an NPC an item or coins. eqgame.exe looks up the NPC's name (which it
# writes), the four item slots (GVW_MyItemSlot0 to 3, EQTypes 3000 to 3003), the four coin buttons (GVW_MyMoney0 to 3:
# platinum, gold, silver and copper, each showing the amount you give as its text), Give and Cancel, and nothing else.
# The user's picks (2026-09-29, from mockups): the four slots in a row on the hot button window's squares under the
# NPC's name, the coins two across under them, then a divider over Give and Cancel. As wide as the hot button
# window, so Give and Cancel have room around their names and a cancel isn't mistaken for Give: as wide as one side
# of the trade window, with the slots two across and the coins stacked, they were no wider than "Cancel".
GIVE_FILE = 'EQUI_GiveWnd.xml'
GIVE_SLOT_COLUMNS = 4  # in reading order, left to right, as the game fills them
GIVE_CONTENT_WIDTH = GIVE_SLOT_COLUMNS * HOT_SIZE + (GIVE_SLOT_COLUMNS - 1) * BUTTON_GAP
GIVE_WIDTH = GIVE_CONTENT_WIDTH + 2 * PADDING
GIVE_RIGHT = GIVE_WIDTH - 2 * BORDER - LEFT
# The name's line at the inside's top, so its ink starts about 7.5px under the window's edge, like the player window's
# name: a label placed into the frame isn't drawn. The slots a padding under its capitals' and digits' ink.
GIVE_NAME_TOP = 0
GIVE_SLOTS_TOP = GIVE_NAME_TOP + PERCENT_INK_TOP + PERCENT_GLYPH_HEIGHT + PADDING
GIVE_SLOT_TYPE = 3000
GIVE_SLOTS = 4
GIVE_SLOT_ROWS = -(-GIVE_SLOTS // GIVE_SLOT_COLUMNS)
# The coin boxes (see COIN_CAPTIONS), (ScreenID, caption) from platinum to copper in reading order, two across (pp gp,
# then sp cp) a padding apart, a padding under the slots.
GIVE_COINS = tuple((f'GVW_MyMoney{n}', caption) for n, caption in enumerate(COIN_CAPTIONS))
GIVE_COIN_COLUMNS = 2
GIVE_COIN_ROWS = -(-len(GIVE_COINS) // GIVE_COIN_COLUMNS)
GIVE_COINS_TOP = GIVE_SLOTS_TOP + GIVE_SLOT_ROWS * HOT_PITCH
GIVE_COINS_BOTTOM = GIVE_COINS_TOP + GIVE_COIN_ROWS * (COIN_HEIGHT + BUTTON_ROW_GAP) - BUTTON_ROW_GAP
# The row divider across the content row a padding under the coins, and Give and Cancel a padding under it (the user's
# request), filling the row: (ScreenID, name, column). The stock ones have no tooltips. They're the confirmation
# dialog's buttons (the user's pick), their names their own text.
GIVE_DIVIDER_TOP = GIVE_COINS_BOTTOM + PADDING
GIVE_BUTTONS_TOP = GIVE_DIVIDER_TOP + DIVIDER_HEIGHT + BUTTON_ROW_GAP
GIVE_HALF_WIDTHS = ((GIVE_CONTENT_WIDTH - BUTTON_GAP) // 2,
                    GIVE_CONTENT_WIDTH - BUTTON_GAP - (GIVE_CONTENT_WIDTH - BUTTON_GAP) // 2)
GIVE_BUTTONS = (('GVW_Give_Button', 'Give', 0), ('GVW_Cancel_Button', 'Cancel', 1))
add_text_buttons(GIVE_HALF_WIDTHS)
GIVE_HEIGHT = 2 * BORDER + GIVE_BUTTONS_TOP + TEXT_BUTTON_HEIGHT + BOTTOM_GAP
# The trade window: what opens when you trade with another player. From eqgame.exe and Zeal's TradeWnd (game_ui.h): the
# client looks up the two names (TRDW_HisName, the other side's, and TRDW_MyName, yours; it writes both), the 16 item
# slots (TRDW_TradeSlot0 to 7 yours and 8 to 15 theirs, EQTypes 3000 to 3015, numbered down each column first in the
# stock window), each side's four coin boxes (TRDW_HisMoney0 to 3 and TRDW_MyMoney0 to 3, see COIN_CAPTIONS), Trade and
# Cancel, and nothing else. The user's picks (2026-09-28, from mockups): the stock arrangement, their side on the left
# and yours on the right, each two slots across over its coins, with the row divider standing between them a padding
# from each; the coins marked, as in the give window; the names in font 3; Trade and Cancel across the bottom.
TRADE_FILE = 'EQUI_TradeWnd.xml'
TRADE_SLOTS = 8  # a side's
TRADE_SLOT_TYPE = 3000
TRADE_SLOT_ROWS = 4
TRADE_SIDE_WIDTH = COIN_WIDTH  # two slots and the padding between them, over a coin box as wide
TRADE_DIVIDER_X = LEFT + TRADE_SIDE_WIDTH + PADDING
# Each side as (ScreenID prefix, x, its first slot's number), in the stock window's order: theirs, then yours.
TRADE_SIDES = (('His', LEFT, TRADE_SLOTS), ('My', TRADE_DIVIDER_X + DIVIDER_HEIGHT + PADDING, 0))
TRADE_RIGHT = TRADE_SIDES[1][1] + TRADE_SIDE_WIDTH
TRADE_WIDTH = TRADE_RIGHT + LEFT + 2 * BORDER
TRADE_CONTENT_WIDTH = TRADE_RIGHT - LEFT
# The names' line at the inside's top, so their ink starts 7.5px under the window's edge (the user's pick, with font 3:
# a label placed into the frame isn't drawn). The slots a padding under their capitals' and digits' ink, the coins a
# padding under the slots.
TRADE_NAME_TOP = 0
TRADE_SLOTS_TOP = TRADE_NAME_TOP + PERCENT_INK_TOP + PERCENT_GLYPH_HEIGHT + PADDING
TRADE_COINS_TOP = TRADE_SLOTS_TOP + TRADE_SLOT_ROWS * HOT_PITCH
TRADE_COINS_BOTTOM = TRADE_COINS_TOP + len(COIN_CAPTIONS) * (COIN_HEIGHT + BUTTON_ROW_GAP) - BUTTON_ROW_GAP
# The divider from the window's padding at the top down to the coins' bottom (see DIVIDER_TEMPLATE).
TRADE_DIVIDER_TOP = LEFT
TRADE_DIVIDER_HEIGHT = TRADE_COINS_BOTTOM - TRADE_DIVIDER_TOP
# The row divider across the content row a padding under the coins and the divider between the sides, and Trade and
# Cancel a padding under it (the user's request), filling the row: (ScreenID, name, column). The stock ones have no
# tooltips. They're the confirmation dialog's buttons, as in the give window.
TRADE_ROW_DIVIDER_TOP = TRADE_COINS_BOTTOM + PADDING
TRADE_BUTTONS_TOP = TRADE_ROW_DIVIDER_TOP + DIVIDER_HEIGHT + BUTTON_ROW_GAP
TRADE_BUTTON_WIDTHS = ((TRADE_CONTENT_WIDTH - BUTTON_GAP) // 2,
                       TRADE_CONTENT_WIDTH - BUTTON_GAP - (TRADE_CONTENT_WIDTH - BUTTON_GAP) // 2)
TRADE_BUTTONS = (('TRDW_Trade_Button', 'Trade', 0), ('TRDW_Cancel_Button', 'Cancel', 1))
add_text_buttons(TRADE_BUTTON_WIDTHS)
TRADE_HEIGHT = 2 * BORDER + TRADE_BUTTONS_TOP + TEXT_BUTTON_HEIGHT + BOTTOM_GAP
# The loot window: a corpse's items. eqgame.exe looks up the corpse's name (LW_CorpseName, which it writes), the slots'
# panel (LootInvWnd) and its 30 slots (LW_LootSlot0 to 29, EQTypes 5000 to 5029), and DoneButton; Zeal looks up
# LinkAllButton and LootAllButton, if there, and makes them do what /linkall and /lootall do. Stock skins lay the slots
# out 2 or 8 across, so XML positions hold. The user's picks (2026-09-28, from mockups): all 30 slots at once, six
# across on the hot button window's squares, so nothing scrolls; the name along the top from the left, as in the give
# window; duxaUI's Link All, Loot All and Done along the bottom.
LOOT_FILE = 'EQUI_LootWnd.xml'
LOOT_SLOTS = 30
LOOT_SLOT_TYPE = 5000
LOOT_COLUMNS = 6
LOOT_ROWS = -(-LOOT_SLOTS // LOOT_COLUMNS)
LOOT_CONTENT_WIDTH = LOOT_COLUMNS * HOT_SIZE + (LOOT_COLUMNS - 1) * BUTTON_GAP
LOOT_WIDTH = LOOT_CONTENT_WIDTH + 2 * PADDING
LOOT_RIGHT = LOOT_WIDTH - 2 * BORDER - LEFT
LOOT_GRID_HEIGHT = LOOT_ROWS * HOT_SIZE + (LOOT_ROWS - 1) * BUTTON_ROW_GAP
# The name's line at the inside's top, its ink 7.5px under the window's edge, as in the give and trade windows; the
# slots a padding under its capitals' and digits' ink.
LOOT_NAME_TOP = 0
LOOT_SLOTS_TOP = LOOT_NAME_TOP + PERCENT_INK_TOP + PERCENT_GLYPH_HEIGHT + PADDING
# The three buttons fill the row a padding under the slots: (ScreenID, name, column). Neither the stock Done nor
# duxaUI's Zeal buttons have tooltips. They're the confirmation dialog's buttons, as in the give window.
LOOT_BUTTONS_TOP = LOOT_SLOTS_TOP + LOOT_GRID_HEIGHT + BUTTON_ROW_GAP
LOOT_BUTTONS = (('LinkAllButton', 'Link All', 0), ('LootAllButton', 'Loot All', 1), ('DoneButton', 'Done', 2))
_LOOT_SPAN = LOOT_CONTENT_WIDTH - (len(LOOT_BUTTONS) - 1) * BUTTON_GAP
LOOT_BUTTON_WIDTHS = tuple(_LOOT_SPAN * (c + 1) // len(LOOT_BUTTONS) - _LOOT_SPAN * c // len(LOOT_BUTTONS)
                           for c in range(len(LOOT_BUTTONS)))
add_text_buttons(LOOT_BUTTON_WIDTHS)
LOOT_HEIGHT = 2 * BORDER + LOOT_BUTTONS_TOP + TEXT_BUTTON_HEIGHT + BOTTOM_GAP
# The bank window. eqgame.exe looks up the banker's name (BW_BankerName, which it writes), the bank's slots
# (BW_BankSlot%d), its four coin boxes (BW_Money0 to 3, see COIN_CAPTIONS) and DoneButton; Zeal looks up ChangeButton,
# if there, and makes it change the bank's coins, then your inventory's (ui_bank.cpp). Quarm's eqgame.dll gives the
# bank 30 slots (EQTypes 2000 to 2029) and a shared bank. The stock window has ten shared slots (BW_SharedBankSlot0 to
# 9, EQTypes 2500 to 2509) and their caption (BW_SharedBankLabel), which nothing looks up: the slots work by their
# EQType. The user's picks (2026-09-29, from mockups): the shared bank on the left, as in the stock window, with
# duxaUI's Change and Done under it; yours on the right, its coins under it two across; the row divider standing
# between them a padding from each, as in the trade window.
BANK_FILE = 'EQUI_BankWnd.xml'
BANK_SLOTS = 30
BANK_SLOT_TYPE = 2000
SHARED_SLOTS = 10
SHARED_SLOT_TYPE = 2500
# Both grids five rows tall and numbered down each column, as the stock window's blocks of ten are, so an item sits
# where players saw it there (less the stock gaps between the blocks).
BANK_ROWS = 5
BANK_COLUMNS = BANK_SLOTS // BANK_ROWS
SHARED_COLUMNS = SHARED_SLOTS // BANK_ROWS
SHARED_WIDTH = COIN_WIDTH  # two slots and the padding between them, over Change and Done as wide
BANK_DIVIDER_X = LEFT + SHARED_WIDTH + PADDING
BANK_X = BANK_DIVIDER_X + DIVIDER_HEIGHT + PADDING
BANK_CONTENT_WIDTH = BANK_COLUMNS * HOT_SIZE + (BANK_COLUMNS - 1) * BUTTON_GAP
BANK_RIGHT = BANK_X + BANK_CONTENT_WIDTH
BANK_WIDTH = BANK_RIGHT + LEFT + 2 * BORDER
BANK_GRID_HEIGHT = BANK_ROWS * HOT_SIZE + (BANK_ROWS - 1) * BUTTON_ROW_GAP
# The caption's and the name's line at the inside's top, their ink 7.5px under the window's edge, as in the trade
# window; the slots a padding under their capitals' ink.
BANK_NAME_TOP = 0
BANK_SLOTS_TOP = BANK_NAME_TOP + PERCENT_INK_TOP + PERCENT_GLYPH_HEIGHT + PADDING
SHARED_CAPTION = 'Shared Bank'  # the stock caption, 71px in font 3
# The band a padding under the slots, two rows a padding apart. Under the shared slots, Change over Done: the
# confirmation dialog's buttons at the loot window's size, with no tooltips (neither duxaUI's nor the stock Done has
# one), as (ScreenID, name, row) in duxaUI's order. Under yours, the coin boxes two across filling the row, wider than
# the give window's so a bank's six or seven digits of platinum clear the coin's name, with the stock tooltips.
BANK_BAND_TOP = BANK_SLOTS_TOP + BANK_GRID_HEIGHT + BUTTON_ROW_GAP
BANK_BAND_HEIGHT = 2 * TEXT_BUTTON_HEIGHT + BUTTON_ROW_GAP
BANK_BUTTONS = (('DoneButton', 'Done', 1), ('ChangeButton', 'Change', 0))
add_text_buttons((SHARED_WIDTH,))
BANK_COIN_COLUMNS = 2
BANK_COIN_WIDTH = (BANK_CONTENT_WIDTH - BUTTON_GAP) // BANK_COIN_COLUMNS
BANK_COINS = tuple((f'BW_Money{n}', caption, f'Drop coins here or click to pick up {coin}')
                   for n, (caption, coin) in enumerate(zip(COIN_CAPTIONS, ('Platinum', 'Gold', 'Silver', 'Copper'))))
# The divider from the window's padding at the top down to the band's bottom (see DIVIDER_TEMPLATE).
BANK_DIVIDER_TOP = LEFT
BANK_DIVIDER_HEIGHT = BANK_BAND_TOP + BANK_BAND_HEIGHT - BANK_DIVIDER_TOP
BANK_HEIGHT = 2 * BORDER + BANK_BAND_TOP + BANK_BAND_HEIGHT + BOTTOM_GAP
# The skills window: your skills in one list straight on the panel, like the raid window's, with Done under it.
# eqgame.exe looks up only SkillList; DoneButton is the stock window's other control. Zeal sorts the list when you
# click the first or third column's heading (ui_manager.cpp, CSkillsWnd's WndNotification), so the client's three
# columns stay in its order. The user's picks (2026-09-29, from mockups): no rank column, 24 rows in view, a fixed size
# with no title bar, so it drags by its background.
SKILLS_FILE = 'EQUI_SkillsWindow.xml'
# The client's three columns, in its order: (heading, width). Each is its widest text in font 3 (Arial 12px) and a
# padding: "Percussion Instruments" 127px (eqstr_en.txt's skill names) and the heading "Value" 32. The rank column
# (eqstr_en.txt's Awful to Master, most likely) has no width and no heading.
SKILLS_COLUMNS = (('Skill', 127 + PADDING), ('', 0), ('Value', 32 + PADDING))
SKILLS_LIST_WIDTH = sum(width for _, width in SKILLS_COLUMNS) + SCROLL_WIDTH
SKILLS_WIDTH = SKILLS_LIST_WIDTH + 2 * PADDING
SKILLS_ROWS = 24  # the raid window's height
SKILLS_LIST_HEIGHT = RAID_HEADER_HEIGHT + SKILLS_ROWS * TEXT_HEIGHT  # the lists' heading row and font 3's lines
# Done a padding under the list and as wide, the confirmation dialog's kind of button, with no tooltip (the stock
# Done has none).
SKILLS_DONE_TOP = LEFT + SKILLS_LIST_HEIGHT + BUTTON_ROW_GAP
add_text_buttons((SKILLS_LIST_WIDTH,))
SKILLS_HEIGHT = 2 * BORDER + SKILLS_DONE_TOP + TEXT_BUTTON_HEIGHT + BOTTOM_GAP
# The compass: two copies of a strip of directions (CompassStrip1 and 2) that the game slides sideways as you turn,
# under an overlay (CompassOverlay) drawn last, all three StaticAnimations the client looks up by ScreenID. Every
# skin keeps the stock strip's 180px, half a pixel a degree, and the marks where the stock art has them: north at
# column 146 (E 11, S 56, W 101), which the game lines up with the stock overlay's pointer at column 49 across the
# inside. The window is the stock one's 106 wide, so however the game works out that line-up, it holds (a 107 wide
# window, which would center the pointer, might put it a pixel off). The user's picks (2026-09-28, from mockups):
# the stock scale, eight directions lettered, north and the pointer in the casting window's soft red.
COMPASS_FILE = 'EQUI_CompassWnd.xml'
COMPASS_STRIPS = ('CompassStrip1', 'CompassStrip2')
COMPASS_STRIP_WIDTH = 180
COMPASS_NORTH_X = 146
COMPASS_POINTER_X = 49
COMPASS_WIDTH = 106
COMPASS_INSIDE_WIDTH = COMPASS_WIDTH - 2 * BORDER
COMPASS_TICK_STEP = COMPASS_STRIP_WIDTH * 10 // 360  # a tick every 10°, as on the stock strip
COMPASS_TICK_HEIGHT = 2
COMPASS_TICKS_HEIGHT = 5  # the tick row: the cardinal ticks and the pointer are this tall
# The letters' ink a padding under the window's edge (our lettering's ink starts at its top), the tick row a padding
# under them, and the edge a padding under that.
COMPASS_LETTERS_TOP = LEFT
COMPASS_TICKS_TOP = COMPASS_LETTERS_TOP + LABEL_HEIGHT + PADDING
COMPASS_INSIDE_HEIGHT = COMPASS_TICKS_TOP + COMPASS_TICKS_HEIGHT + LEFT
COMPASS_HEIGHT = COMPASS_INSIDE_HEIGHT + 2 * BORDER
# The overlay hides the strip within the window's padding and fades it in over this much more, so letters slide in and
# out softly instead of being cut off.
COMPASS_FADE = PADDING
COMPASS_NORTH_RGB = SPELL_RGB
# (label, degrees clockwise from north, color). With every capital 5 wide, a cardinal's label is centered on its tick's
# column and an intercardinal's (12 wide) on the line between two columns, where a half-degree-a-pixel strip puts it.
COMPASS_MARKS = (('N', 0, COMPASS_NORTH_RGB), ('NE', 45, PET_RGB), ('E', 90, TEXT_RGB), ('SE', 135, PET_RGB),
                 ('S', 180, TEXT_RGB), ('SW', 225, PET_RGB), ('W', 270, TEXT_RGB), ('NW', 315, PET_RGB))
# The spell book: its two pages side by side, each a table of eight rows in the spell bar's look (the user's pick,
# 2026-09-29, from a mockup), a divider standing between them; a thin bar along the top for memorizing or scribing,
# like the spell bar's recovery bar; the page arrows, both page numbers and Done along the bottom. eqgame.exe looks up
# SBW_Spell%d and SBW_SpellName%d (16 of each), SBW_PageDown_Button and SBW_PageUp_Button, SBW_MemPage0_Button and
# SBW_MemPage1_Button (no size in every skin), SBW_LeftPageNum and SBW_RightPageNum, and DoneButton; the bars by
# EQType, 9 memorizing and 10 scribing, which never run together, so they share a spot (as in duxaUI). The stock
# book art (SBW_SpellBook1 to 4) is nothing the client looks up, so it's left out. The names and page numbers are
# StaticText, which takes no click (see static_text()).
SPELLBOOK_FILE = 'EQUI_SpellBookWnd.xml'
BOOK_SPELLS = 16
BOOK_PAGE_ROWS = 8
# Room for the longest name any class can scribe (spells_en.txt), 177px in font 3 (Arial 12px).
BOOK_NAME_WIDTH = 178
BOOK_PAGE_WIDTH = GEM_ICON + PADDING + BOOK_NAME_WIDTH  # a page's icons and names, which its row dividers span
# The client paints a detrimental spell's slot RedIconBackground, the Effects window's art, from the slot's top left at
# its own size, which put its bars over the names (seen in game 2026-09-29). So each slot starts this far left of its
# icon and this far above it, and the bars (4 + 16 + 4 = 24px wide, 16 tall, see HARMFUL_BARS) fall under the spell's
# 24px icon, opaque there in every A_SpellIcons cell. Each page's icons stand that far in (the user's pick):
# panel-colored patches over the bars would show at any Alpha under 255.
BOOK_ICON_X = HARMFUL_BARS[0] - SLOT_X
BOOK_ICON_Y = ROW_ICON_MARGIN
BOOK_SLOT_WIDTH = BOOK_ICON_X + BOOK_PAGE_WIDTH
BOOK_SLOT_HEIGHT = GEM_ROW_HEIGHT - (GEM_ICON_MARGIN - BOOK_ICON_Y)  # to the row's bottom
BOOK_DIVIDER_X = LEFT + BOOK_SLOT_WIDTH + PADDING
BOOK_PAGE_XS = (LEFT + BOOK_ICON_X, BOOK_DIVIDER_X + DIVIDER_HEIGHT + PADDING + BOOK_ICON_X)  # each page's icons
BOOK_RIGHT = BOOK_PAGE_XS[1] + BOOK_PAGE_WIDTH
BOOK_CONTENT_WIDTH = BOOK_RIGHT - LEFT
SPELLBOOK_WIDTH = BOOK_RIGHT + LEFT + 2 * BORDER
MEMORIZE_TYPE = 9
SCRIBE_TYPE = 10
BOOK_BAR_TOP = LEFT
# The first row's icon a padding under the bar; the rows the spell bar's, a divider under each (the last one's across
# both pages, meeting the one standing between them), and the band a padding under that.
BOOK_ROWS_TOP = BOOK_BAR_TOP + TICK_HEIGHT + PADDING - GEM_ICON_MARGIN
BOOK_LAST_DIVIDER_TOP = BOOK_ROWS_TOP + BOOK_PAGE_ROWS * GEM_ROW_PITCH - DIVIDER_HEIGHT
BOOK_BAND_TOP = BOOK_LAST_DIVIDER_TOP + DIVIDER_HEIGHT + PADDING
# The page arrows at the band's ends, the Actions window's (see SOCIAL_ARROWS); Done the loot and bank windows',
# centered on the divider between the pages.
BOOK_ARROWS = (('SBW_PageDown_Button', 'Previous Page', 'Left'), ('SBW_PageUp_Button', 'Next Page', 'Right'))
BOOK_DONE_WIDTH = COIN_WIDTH
add_text_buttons((BOOK_DONE_WIDTH,))
SPELLBOOK_HEIGHT = 2 * BORDER + BOOK_BAND_TOP + TEXT_BUTTON_HEIGHT + BOTTOM_GAP
# The inventory window: what you wear, your stats and your coins. eqgame.exe looks up the worn and bag slots
# (InvSlot%d, EQTypes 1 to 29), the coin boxes (IW_Money0 to 3, see COIN_CAPTIONS), IW_Skills, IW_AltAdvBtn,
# IW_Destroy and DoneButton, the class picture (ClassAnim, which it sets to A_ClassAnim%02d), the area a dropped item
# is equipped from (IW_CharacterView), and the AA caption and bar (AltAdvLabel, AltAdvGauge); every other text is a
# label the client fills by its EQType. The user's picks (2026-09-29, from mockups): EverQuest's arrangement, the worn
# slots around a middle showing who you are and your XP and AA, your stats, AC, ATK and weight and your coins in a
# column on the right, and the buttons along the bottom; the deity, but no HP or resists (the player window has them),
# no class picture and no bag slots, which the hot button window has.
INVENTORY_FILE = 'EQUI_Inventory.xml'
# The worn slots on the hot button window's squares, five columns and seven rows: (EQType, the empty slot's icon,
# half-column, row), in EQType order. Each is in the stock window's column, and its row but for Legs and Feet, which sit
# centered between the rings, a row higher than there, and the weapons centered under them; so on half-columns.
INV_WORN = (
    (1, 'Ear', 0, 0), (2, 'Head', 4, 0), (3, 'Face', 6, 0), (4, 'Ear', 8, 0), (5, 'Neck', 2, 0),
    (6, 'Shoulders', 8, 2), (7, 'Arms', 0, 2), (8, 'Back', 8, 1), (9, 'Wrist', 0, 3), (10, 'Wrist', 8, 3),
    (11, 'Range', 5, 6), (12, 'Hands', 8, 4), (13, 'Primary', 1, 6), (14, 'Secondary', 3, 6), (15, 'Fingers', 0, 5),
    (16, 'Fingers', 8, 5), (17, 'Chest', 0, 1), (18, 'Legs', 3, 5), (19, 'Feet', 5, 5), (20, 'Waist', 0, 4),
    (21, 'Ammo', 7, 6),
)
INV_BAG_TYPES = range(22, 30)  # the bag slots, which the client looks up: kept with no size
INV_COLUMNS = 5
INV_ROWS = 7
INV_DOLL_WIDTH = INV_COLUMNS * HOT_SIZE + (INV_COLUMNS - 1) * BUTTON_GAP
INV_DOLL_HEIGHT = INV_ROWS * HOT_SIZE + (INV_ROWS - 1) * BUTTON_ROW_GAP
# The middle: the three columns between the side ones, over the four rows between the top row and Legs and Feet.
# IW_CharacterView covers it, see-through, so an item dropped anywhere on it is equipped, and the text lies over it.
INV_MIDDLE_X = LEFT + HOT_PITCH
INV_MIDDLE_TOP = LEFT + HOT_PITCH
INV_MIDDLE_WIDTH = 3 * HOT_SIZE + 2 * BUTTON_GAP
INV_MIDDLE_HEIGHT = 4 * HOT_SIZE + 3 * BUTTON_ROW_GAP
INV_MIDDLE_RIGHT = INV_MIDDLE_X + INV_MIDDLE_WIDTH
INV_DROP_TOOLTIP = 'Drop Item Here to Auto Equip'  # the stock window's
# The middle in sections: who you are (the name, the level and class, the deity in the overlay's grey), lines stacked on
# their height, then XP and AA (the user moved them here from the column), like the player window's health and mana: a
# caption with the % at the line's end and the bar under it, across the middle. The first line's ink a padding under the
# top row, each section two paddings under the digits or bar of the one above, like the player window's sections.
# Labels 26 and 27 are the XP and AA %, gauges 4 and 5 their bars.
INV_SECTION_STEP = math.ceil(PERCENT_INK_TOP + PERCENT_GLYPH_HEIGHT + 2 * PADDING - TEXT_INK_TOP)
INV_WHO_TOP = math.ceil(LEFT + HOT_SIZE + PADDING - TEXT_INK_TOP)
INV_XP_TOP = INV_WHO_TOP + 2 * TEXT_HEIGHT + INV_SECTION_STEP
INV_AA_TOP = INV_XP_TOP + PLAYER_SECTION_PITCH
# (caption's ScreenID, caption, % label, gauge's ScreenID, gauge EQType, top). The client looks up AltAdvLabel and
# AltAdvGauge and hid both in game, leaving AA's line a bare 0%; the user wants the line always, so AA's caption and bar
# have no ScreenID (the bar works by its EQType) and the stock two stay, hidden (INV_HIDDEN_AA).
INV_PROGRESS = (('NextLevelLabel', 'XP', 26, 'ExpGauge', 4, INV_XP_TOP),
                (None, 'AA', 27, None, 5, INV_AA_TOP))
INV_HIDDEN_AA = ('AltAdvLabel', 'AltAdvGauge')
# Both bars in their percentages' golden yellow (GOLD_RGB, the user's request), solid like the mana bar so they show it
# whole: at the other bars' 70% over the panel it would darken toward olive.
INV_LEVEL_WIDTH = 2 * DIGIT_WIDTH  # the level, right-aligned against the class a space after it
# The column on the right, three slots wide, the row divider standing between it and the worn slots a padding from each.
INV_DIVIDER_X = LEFT + INV_DOLL_WIDTH + PADDING
INV_COLUMN_X = INV_DIVIDER_X + DIVIDER_HEIGHT + PADDING
INV_COLUMN_WIDTH = 3 * HOT_SIZE + 2 * BUTTON_GAP
INV_RIGHT = INV_COLUMN_X + INV_COLUMN_WIDTH
INV_WIDTH = INV_RIGHT + LEFT + 2 * BORDER
INV_CONTENT_WIDTH = INV_RIGHT - LEFT
# Your stats, one to a line from the inside's top, their ink 7.5px under the window's edge like the bank window's names
# (a label placed into the frame isn't drawn): (caption, label EQType), in the stock order. Each caption and number
# keeps its stock ScreenID, the caption's and 'NumberLabel'.
INV_STATS = (('STR', 5), ('STA', 6), ('AGI', 8), ('DEX', 7), ('WIS', 9), ('INT', 10), ('CHA', 11))
INV_STATS_TOP = 0
# Under the stats (the user moved them here from the middle): AC and ATK, as the stats (caption, label EQType), then the
# weight as the player window's current/max (labels 24 and 25). Each is set apart from what's above by the row divider
# across the column (the user's request), a padding under the digits above and a padding over the next ink, as the
# group window's members are.
INV_DIGITS_BOTTOM = PERCENT_INK_TOP + PERCENT_GLYPH_HEIGHT  # down a line of font 3 to its digits' bottom
INV_STATS_DIVIDER_TOP = INV_STATS_TOP + (len(INV_STATS) - 1) * TEXT_HEIGHT + INV_DIGITS_BOTTOM + PADDING
INV_NUMBERS_TOP = INV_STATS_DIVIDER_TOP + DIVIDER_HEIGHT + DIVIDER_TO_NAME
INV_NUMBERS = (('AC', 22), ('ATK', 23))
INV_NUMBERS_DIVIDER_TOP = INV_NUMBERS_TOP + (len(INV_NUMBERS) - 1) * TEXT_HEIGHT + INV_DIGITS_BOTTOM + PADDING
INV_WEIGHT_TOP = INV_NUMBERS_DIVIDER_TOP + DIVIDER_HEIGHT + DIVIDER_TO_NAME
INV_COLUMN_DIVIDERS = (('TUI_IW_StatsDivider', INV_STATS_DIVIDER_TOP), ('TUI_IW_NumbersDivider', INV_NUMBERS_DIVIDER_TOP))
# The coin boxes stacked at the column's foot, the last level with the worn slots' bottom. The column is as wide as the
# bank's coin boxes, so they share its art.
INV_COIN_PITCH = COIN_HEIGHT + BUTTON_ROW_GAP
INV_COINS_TOP = LEFT + INV_DOLL_HEIGHT - len(COIN_CAPTIONS) * INV_COIN_PITCH + BUTTON_ROW_GAP
# The stock window's HP and resists, which the player window shows instead (the user): kept as labels, hidden.
INV_HIDDEN_LABELS = tuple(f'{shown}{kind}' for shown in ('HP', 'Poison', 'Magic', 'Disease', 'Fire', 'Cold')
                          for kind in ('Label', 'NumberLabel'))
# Along the bottom a padding under the worn slots, filling the row: (ScreenID, name, column), the confirmation dialog's
# buttons, with no tooltips (the stock ones have none).
INV_BUTTONS_TOP = LEFT + INV_DOLL_HEIGHT + BUTTON_ROW_GAP
INV_BUTTONS = (('IW_Skills', 'Skills', 0), ('IW_AltAdvBtn', 'AA', 1), ('IW_Destroy', 'Destroy', 2),
               ('DoneButton', 'Done', 3))
_INV_SPAN = INV_CONTENT_WIDTH - (len(INV_BUTTONS) - 1) * BUTTON_GAP
INV_BUTTON_WIDTHS = tuple(_INV_SPAN * (c + 1) // len(INV_BUTTONS) - _INV_SPAN * c // len(INV_BUTTONS)
                          for c in range(len(INV_BUTTONS)))
add_text_buttons(INV_BUTTON_WIDTHS)
INV_HEIGHT = 2 * BORDER + INV_BUTTONS_TOP + TEXT_BUTTON_HEIGHT + BOTTOM_GAP
# The tracking window: which con colors to list, how to sort and whether to list players, then what's in range to track,
# then Track and Cancel. The stock window's every control is kept: the filters (six checkboxes), the list, the two
# dropdowns (Combobox) and their captions, Track and DoneButton, and the "Filters" caption, hidden. The client fills
# the list and the dropdowns' choices (the stock file gives none). The user's picks (2026-09-29, from mockups): the
# settings above the list, each filter a square of its con color, 24 names in view, as wide as the hot button window,
# a fixed size with no title bar, so it drags by its background.
TRACKING_FILE = 'EQUI_TrackingWnd.xml'
TRACK_WIDTH = HOT_WIDTH
TRACK_RIGHT = TRACK_WIDTH - 2 * BORDER - LEFT
TRACK_CONTENT_WIDTH = TRACK_RIGHT - LEFT
# The filters, one row filling the content row: (ScreenID, color's name, tooltip, con color), in the stock order. The
# colors are the stock buttons' letters'; the tooltips take eqstr_en.txt's words ("You will see %1 NPCs when tracking").
TRACK_FILTERS = (
    ('TRW_FilterRedButton', 'Red', 'Red NPCs', (240, 0, 0)),
    ('TRW_FilterYellowButton', 'Yellow', 'Yellow NPCs', (240, 240, 0)),
    ('TRW_FilterWhiteButton', 'White', 'White NPCs', (240, 240, 240)),
    ('TRW_FilterBlueButton', 'Blue', 'Blue NPCs', (0, 0, 240)),
    ('TRW_FilterLightBlueButton', 'LightBlue', 'Light blue NPCs', (0, 240, 240)),
    ('TRW_FilterGreenButton', 'Green', 'Green NPCs', (0, 240, 0)),
)
FILTER_SIZE = (TRACK_CONTENT_WIDTH - (len(TRACK_FILTERS) - 1) * BUTTON_GAP) // len(TRACK_FILTERS)
FILTER_TOP = LEFT
# Each filter a selector toggle with a square of its color in the middle, bright while the color is listed (the
# checkbox pressed, which is assumed) and dimmed while it's filtered out. Alphas on the steps.
FILTER_SWATCH = 10
SWATCH_RADIUS = 2
SWATCH_ALPHA = {'Normal': 85, 'Flyby': 170, 'Pressed': 255, 'PressedFlyby': 255}  # TOGGLE_LOOKS' states
# The dropdowns: as tall as the dialogs' buttons, on the panel with a 1px outline in the edge's color (COMBO_TEMPLATE,
# opaque, since an open dropdown lies over the list), the scrollbar's chevron at the right. Each a padding under
# what's above it, with its caption to its left, the captions' ink centered on the boxes like the Actions window's page
# number on its arrows, and the boxes a padding after the wider caption, "Players" (41px in Arial 12).
COMBO_TEMPLATE = 'WDT_TriageCombo'
COMBO_BUTTON = 'TUI_Combo'
COMBO_HEIGHT = TEXT_BUTTON_HEIGHT
COMBO_ARROW_HEIGHT = COMBO_HEIGHT - 2  # inside the outline
# How tall the open list is: its choices' rows and the outline. A row is assumed 16px: Zeal's options give four
# choices ListHeight 70.
COMBO_ROW_HEIGHT = 16
TRACK_CAPTION_WIDTH = 41
TRACK_COMBO_X = LEFT + TRACK_CAPTION_WIDTH + PADDING
TRACK_COMBO_WIDTH = TRACK_RIGHT - TRACK_COMBO_X
TRACK_CAPTION_DROP = round(COMBO_HEIGHT / 2 - DIGITS_INK_MIDDLE)
TRACK_SORT_TOP = FILTER_TOP + FILTER_SIZE + BUTTON_ROW_GAP
TRACK_PLAYERS_TOP = TRACK_SORT_TOP + COMBO_HEIGHT + BUTTON_ROW_GAP
# (caption's ScreenID, caption, the box's ScreenID, top, the choices: /tracksort's five and /trackplayers' three)
TRACK_COMBOS = (('TRW_TrackSortLabel', 'Sort', 'TRW_TrackSortCombobox', TRACK_SORT_TOP, 5),
                ('TRW_TrackPlayersLabel', 'Players', 'TRW_TrackPlayersCombobox', TRACK_PLAYERS_TOP, 3))
# The list: no heading, so its first name's ink (and the scrollbar's up arrow's) a padding under the Players box. One
# column, the stock one's 150px, and the scrollbar fill the content row.
TRACK_LIST_TOP = TRACK_PLAYERS_TOP + COMBO_HEIGHT + DIVIDER_TO_NAME
TRACK_ROWS = 24
TRACK_LIST_HEIGHT = TRACK_ROWS * TEXT_HEIGHT
TRACK_COLUMNS = (('', TRACK_CONTENT_WIDTH - SCROLL_WIDTH),)
# Track and Cancel (the stock words) a padding under the list, filling the row: the confirmation dialog's kind of
# button, at the Actions window's widths, with no tooltips (the stock ones have none).
TRACK_BUTTONS_TOP = TRACK_LIST_TOP + TRACK_LIST_HEIGHT + BUTTON_ROW_GAP
TRACK_BUTTONS = (('TRW_TrackButton', 'Track'), ('DoneButton', 'Cancel'))
_TRACK_SPAN = TRACK_CONTENT_WIDTH - (len(TRACK_BUTTONS) - 1) * BUTTON_GAP
TRACK_BUTTON_WIDTHS = tuple(_TRACK_SPAN * (c + 1) // len(TRACK_BUTTONS) - _TRACK_SPAN * c // len(TRACK_BUTTONS)
                            for c in range(len(TRACK_BUTTONS)))
add_text_buttons(TRACK_BUTTON_WIDTHS)
TRACK_HEIGHT = 2 * BORDER + TRACK_BUTTONS_TOP + TEXT_BUTTON_HEIGHT + BOTTOM_GAP
# The Alternate Advancement window: a tab for each kind of ability over its list, the selected ability's description
# under them, and a column on the right with your AA XP, how much of your XP goes to AA, your points and the ability's
# reuse timer, then Train, Hotkey and Done. eqgame.exe looks up the tab box (Subwindows), its pages and their lists
# (Page%d and List%d, 1 to 5), Description, ExpCount, CurrentCount, TotalCount, Timer, LessExpButton, MoreExpButton,
# TrainButton, HotButton and DoneButton, and fills them all; the bar works by its EQType (5), and nothing looks up the
# stock captions, which keep their ScreenIDs as ours. The user's pick (2026-09-29, from mockups): the stock arrangement,
# a fixed size with no title bar, so it drags by its background.
AA_FILE = 'EQUI_AAWindow.xml'
# The stock pages in the stock order: (page's ScreenID, list's ScreenID, name on its tab, the tab art's name).
AA_PAGES = (('Page1', 'List1', 'General', 'AAGeneral'), ('Page2', 'List2', 'Archetype', 'AAArchetype'),
            ('Page3', 'List3', 'Class', 'AAClass'), ('Page4', 'List4', 'PoP Advance', 'AAPoPAdvance'),
            ('Page5', 'List5', 'PoP Ability', 'AAPoPAbility'))
# The tabs are laid out as the Actions window's, with the same tab and page border templates (see PAGE_RIGHT), each
# wide enough for "PoP Advance" in font 2 (64px) and a padding either side; the list and the description fill the row.
# The tab box ends where the divider standing beside the list is.
AA_TAB_WIDTH = 64 + 2 * PADDING
AA_LIST_WIDTH = len(AA_PAGES) * (AA_TAB_WIDTH + BUTTON_GAP) - BUTTON_GAP
AA_TAB_WIDTHS, AA_TAB_LEFTS = tab_row(AA_LIST_WIDTH, len(AA_PAGES))
AA_TAB_BOX_WIDTH = AA_LIST_WIDTH + BUTTON_GAP + 2 * TAB_CORNER
# Each tab's name (the AA and friends windows'), painted on in the Actions tabs' icons' color, since where the tab box
# would write a page's TabText isn't known: the ink's coverage as tools/preview.py draws font 2 centered on the tab, as
# for Close (see CLOSE_INK), as (its top left in the tab, rows). The friends window's tabs are 78px wide, the AA's 76.
TAB_INK = {
    'General': ((19, 10), (
        '02aeeb3000000000000000000000000000058',
        '0d7116c000000000000000000000000000058',
        '5b00001009ed305bde6009ed305ae59ed4058',
        '7800dff26913d05c14d06913d05c16a14c058',
        '5b0000c29ffff15800d09ffff158018bed058',
        '0d7115e27910005800d07910005808936d058',
        '02aefb400aee905800d00aee905804ee7d058',
    )),
    'Archetype': ((14, 10), (
        '007e0000000000058000000000016000000000000000000',
        '00c9600000000005800000000003a000000000000000000',
        '0492c005ae5aec25ace6009ed30cf9a502b59de5009ed30',
        '0a40b305c17a16a5c23d06913d03a04a0855c13d06913d0',
        '1ffffa0580950005800d09ffff13a00c2d05700c29ffff1',
        '69001e15806a14b5800d07910003b006b805c13d0791000',
        'c3000975800aec35800d00aee901d901f305bdd400aee90',
        '00000000000000000000000000000003c00580000000000',
        '0000000000000000000000000000006e300580000000000',
    )),
    'Class': ((25, 10), (
        '02bee80580000000000000000',
        '1d612b6580000000000000000',
        '6a000125809ed402cfc22cfc2',
        '7800000585a14c07a2007a200',
        '5a000255818bed02bfd32bfd3',
        '1d612b7588936d00018800188',
        '03cee80584ee7d05dfc25dfc2',
    )),
    'PoP Advance': ((6, 10), (
        '4fffe700000004fffe70000007e0000000d00000000000000000000000000000',
        '4b002e20000004b002e200000c96000000d00000000000000000000000000000',
        '4b002d20aed404b002d20000492c001be8d0a403a09ed405bde600aec209ed30',
        '4fffd707a13d14fffd700000a40b307916d0490945a14c05c14d06a16a6913d0',
        '4b000009400b24b000000001ffffa09400d00c1c018bed05800d0950009ffff1',
        '4b000007a13e14b0000000069001e17a15d007a808936d05800d06a14b791000',
        '4b000001aed504b00000000c3000970af9c002f204ee7d05800d00aec30aee90',
    )),
    'PoP Ability': ((13, 10), (
        '4fffe700000004fffe70000007e00058000058585816000000',
        '4b002e20000004b002e200000c96005800000058003a000000',
        '4b002d20aed404b002d20000492c005add50585858cf9a502b',
        '4fffd707a13d14fffd700000a40b305c13d05858583a04a085',
        '4b000009400b24b000000001ffffa05700c25858583a00c2d0',
        '4b000007a13e14b0000000069001e15c13d05858583b006b80',
        '4b000001aed504b00000000c3000975add405858581d901f30',
        '00000000000000000000000000000000000000000000003c00',
        '0000000000000000000000000000000000000000000006e300',
    )),
    'Friends': ((22, 10), (
        '3ffffa000580000000000000000d000000',
        '3c0000000000000000000000000d000000',
        '3c00005ae8809ed305bde601be8d02cfc2',
        '3ffff25c1586913d05c14d07916d07a200',
        '3c0000580589ffff15800d09400d02bfd3',
        '3c0000580587910005800d07a15d000188',
        '3c0000580580aee905800d00af9c05dfc2',
    )),
    'Ignored': ((21, 10), (
        '1d00000000000000000000000000000000d',
        '1d00000000000000000000000000000000d',
        '1d01be9c05bde600aed405ae59ed301be8d',
        '1d07915d05c14d07a13d15c17913d07916d',
        '1d0a400d05800d09400b25809ffff19400d',
        '1d07915d05800d07a13e15807910007a15d',
        '1d01ae8d05800d01aed505800aee900af9c',
        '0006906b000000000000000000000000000',
        '0001bfd3000000000000000000000000000',
    )),
}
# Each list's three columns, in the client's order: (heading, width). The rank and cost are each their widest text in
# font 3 (Arial 12px) and a padding: "10/10" (31px; the client writes "%d/%d") and the heading "Cost" (25). The names
# take the rest, where eqstr_en.txt's widest, "Spell Casting Reinforcement Mastery", is 202px. 18 rows in view (the
# user's pick), most of a tab's abilities.
AA_RANK_WIDTH = 31 + PADDING
AA_COST_WIDTH = 25 + PADDING
AA_COLUMNS = (('Ability', AA_LIST_WIDTH - SCROLL_WIDTH - AA_RANK_WIDTH - AA_COST_WIDTH), ('Rank', AA_RANK_WIDTH),
              ('Cost', AA_COST_WIDTH))
AA_ROWS = 18
AA_LIST_HEIGHT = RAID_HEADER_HEIGHT + AA_ROWS * TEXT_HEIGHT
AA_TAB_BOX_HEIGHT = PAGE_TOP + AA_LIST_HEIGHT + LEFT  # the page border's bottom under the list (see PAGE_BORDER_PIECES)
# The selected ability's description, the client's text (eqstr_en.txt: the ability's own, then whether it's activated
# and its refresh time, or passive), under the row divider a padding under the list, its first line's ink a padding
# under that. Six lines in view: at this width the longest description takes seven, most four or fewer.
AA_DIVIDER_TOP = PAGE_TOP + AA_LIST_HEIGHT + PADDING
AA_DESCRIPTION_TOP = AA_DIVIDER_TOP + DIVIDER_HEIGHT + DIVIDER_TO_NAME
AA_DESCRIPTION_LINES = 6
AA_BOTTOM = AA_DESCRIPTION_TOP + AA_DESCRIPTION_LINES * TEXT_HEIGHT
# The column, three slots wide like the inventory's, with the row divider standing between it and the list a padding
# from each, from the window's top padding to its bottom one.
AA_DIVIDER_X = LEFT + AA_LIST_WIDTH + PADDING
AA_COLUMN_X = AA_DIVIDER_X + DIVIDER_HEIGHT + PADDING
AA_COLUMN_WIDTH = 3 * HOT_SIZE + 2 * BUTTON_GAP
AA_RIGHT = AA_COLUMN_X + AA_COLUMN_WIDTH
AA_WIDTH = AA_RIGHT + LEFT + 2 * BORDER
AA_HEIGHT = 2 * BORDER + AA_BOTTOM + BOTTOM_GAP
# The column's sections, two paddings apart like the inventory's: your AA XP, its % (label 27) and bar as the inventory's,
# the first line at the inside's top like the inventory's stats (its ink 7.5px under the edge); how much of your XP goes
# to AA, a caption over the client's % between - and + (the social page arrows' size, the digits' ink centered on
# them); then your points, those spent and the selected ability's reuse timer, stacked on their line height.
AA_XP_TOP = 0
AA_SPLIT_TOP = AA_XP_TOP + PLAYER_SECTION_PITCH
AA_SPLIT_ROW_TOP = AA_SPLIT_TOP + PERCENT_INK_TOP + PERCENT_GLYPH_HEIGHT + PADDING
AA_NUMBERS_TOP = AA_SPLIT_ROW_TOP + ARROW_SIZE + math.ceil(2 * PADDING - TEXT_INK_TOP)
# (caption's ScreenID, caption, value's ScreenID), each value in the game's green ending at the column's right: the
# stock captions' ScreenIDs, which nothing looks up; the timer's caption is ours.
AA_NUMBERS = (('CurrentLabel', 'Points', 'CurrentCount'), ('TotalLabel', 'Spent', 'TotalCount'),
              (None, 'Reuse', 'Timer'))
AA_VALUE_WIDTH = 48  # "00:00:00" in font 3 (Arial 12px): the timer's "%02d:%02d:%02d", the longest value
# Train, Hotkey and Done down the column's foot, Done's bottom level with the description's: the confirmation dialog's
# kind of button, a padding apart, with no tooltips (the stock ones have none).
AA_BUTTONS = (('TrainButton', 'Train'), ('HotButton', 'Hotkey'), ('DoneButton', 'Done'))
AA_BUTTONS_TOP = AA_BOTTOM - len(AA_BUTTONS) * (TEXT_BUTTON_HEIGHT + BUTTON_ROW_GAP) + BUTTON_ROW_GAP
add_text_buttons((AA_COLUMN_WIDTH,))
# The friends window: your friends and the players you ignore, each on a tab over its list, with the name field and Add
# under the list, then Delete, and on the friends' tab Contact and Who. eqgame.exe's strings name the tab box
# (Subwindows), both lists, both name fields and every button; the stock pages have no ScreenID. The user's pick
# (2026-09-29, from a mockup): the tabs as words, like the AA window's, as wide as the Actions window, a fixed size with
# no title bar, so it drags by its background.
FRIENDS_FILE = 'EQUI_FriendsWnd.xml'
# The stock pages in the stock order: (page's ScreenID, name on its tab and its art's name, the list, the name field,
# Add, Delete, and the buttons after Delete as (ScreenID, name)). The pages' ScreenIDs are ours.
FRIENDS_PAGES = (
    ('FriendsPage', 'Friends', 'FriendsList', 'NameInput', 'AddButton', 'DeleteButton',
     (('ContactButton', 'Contact'), ('WhoButton', 'Who'))),
    ('IgnorePage', 'Ignored', 'IgnoreList', 'IgnoreNameInput', 'IgnoreAddButton', 'IgnoreDeleteButton', ()),
)
FRIENDS_WIDTH = ACTIONS_WIDTH
FRIENDS_CONTENT_WIDTH = ACTIONS_CONTENT_WIDTH
FRIENDS_TAB_WIDTHS, FRIENDS_TAB_LEFTS = tab_row(FRIENDS_CONTENT_WIDTH, len(FRIENDS_PAGES))
# Each list with no heading, like the stock ones, so its page starts higher (see LIST_PAGE_BORDER): one column, the
# names, and the scrollbar across the content row, 12 names in view.
FRIENDS_ROWS = 12
FRIENDS_LIST_HEIGHT = FRIENDS_ROWS * TEXT_HEIGHT
FRIENDS_COLUMNS = (('', FRIENDS_CONTENT_WIDTH - SCROLL_WIDTH),)
# Under the list the name field and Add, then Delete, Contact and Who, in thirds of the row: the field spans two, Add
# is over Who, and Delete is in the same spot on both tabs. The field looks like the quantity window's; the buttons are
# the confirmation dialog's kind, with no tooltips (the stock ones have none).
FRIENDS_COLUMN_COUNT = 3
_FRIENDS_SPAN = FRIENDS_CONTENT_WIDTH - (FRIENDS_COLUMN_COUNT - 1) * BUTTON_GAP
FRIENDS_THIRDS = tuple(_FRIENDS_SPAN * (c + 1) // FRIENDS_COLUMN_COUNT - _FRIENDS_SPAN * c // FRIENDS_COLUMN_COUNT
                       for c in range(FRIENDS_COLUMN_COUNT))
FRIENDS_LEFTS = tuple(sum(FRIENDS_THIRDS[:c]) + c * BUTTON_GAP for c in range(FRIENDS_COLUMN_COUNT))
FRIENDS_FIELD_TOP = FRIENDS_LIST_HEIGHT + BUTTON_ROW_GAP
FRIENDS_FIELD_WIDTH = FRIENDS_LEFTS[-1] - BUTTON_GAP
FRIENDS_BUTTONS_TOP = FRIENDS_FIELD_TOP + INPUT_HEIGHT + BUTTON_ROW_GAP
FRIENDS_PAGE_HEIGHT = FRIENDS_BUTTONS_TOP + TEXT_BUTTON_HEIGHT
FRIENDS_HEIGHT = 2 * BORDER + LIST_PAGE_TOP + FRIENDS_PAGE_HEIGHT + LEFT
add_text_buttons(FRIENDS_THIRDS)

# Every SIDL file starts like this; the client is picky about these lines (see Zeal's generate_big_xml.py).
XML_HEADER = (
    '<?xml version="1.0" encoding="us-ascii"?>',
    '<XML ID="EQInterfaceDefinitionLanguage">',
    '  <Schema xmlns="EverQuestData" xmlns:dt="EverQuestDataTypes" />',
)
BUTTON_STATES = ('Normal', 'Pressed', 'Flyby', 'Disabled', 'PressedFlyby')
# The window frame's sides, each drawn with one of our pieces. Corners have their own; the side
# pieces next to a corner (LeftTop, LeftBottom and so on) reuse the plain side.
BORDER_PIECES = {
    'TopLeft': 'TopLeft', 'Top': 'Top', 'TopRight': 'TopRight',
    'RightTop': 'Right', 'Right': 'Right', 'RightBottom': 'Right',
    'BottomRight': 'BottomRight', 'Bottom': 'Bottom', 'BottomLeft': 'BottomLeft',
    'LeftTop': 'Left', 'Left': 'Left', 'LeftBottom': 'Left',
}
FRAME_TEMPLATE = 'WDT_Triage'
FIELD_TEMPLATE = 'WDT_TriageField'
# The chat input box's template: a clear background and a clear border, so the box itself draws nothing and
# only the strip under it shows. With the field's template, the user saw a second box under the input box
# in game: an Editbox seems to draw its template's background even when marked see-through. The raid window's
# lists use it too: they sit on the window's panel with only our slim scrollbar drawn.
EDIT_TEMPLATE = 'WDT_TriageClear'
# A divider standing up (the trade window's, see vertical_divider()): a child window 1px wide drawing the row
# divider's color as its background, with no border. A piece as tall as the trade window's (283px) doesn't fit in
# the atlas, which packs pieces in rows as tall as their tallest and has less than that left.
DIVIDER_TEMPLATE = 'WDT_TriageDivider'


class BuildError(Exception):
    pass


class Texture:
    """An RGBA image as rows of (r, g, b, a) tuples, top row first."""

    def __init__(self, width, height, color=CLEAR):
        self.width, self.height = width, height
        self.rows = [[color] * width for _ in range(height)]

    def pixel(self, x, y):
        return self.rows[y][x]

    def crop(self, x, y, width, height):
        piece = Texture(width, height)
        piece.rows = [row[x:x + width] for row in self.rows[y:y + height]]
        return piece

    def repeated(self, width, height):
        # Tiles this texture to the given size, as the client does along a window's sides.
        tiled = Texture(width, height)
        tiled.rows = [[self.rows[y % self.height][x % self.width] for x in range(width)] for y in range(height)]
        return tiled

    def paste(self, other, x, y):
        for row_index, row in enumerate(other.rows):
            self.rows[y + row_index][x:x + other.width] = row


def over(color, coverage, under=CLEAR):
    """color, its alpha scaled by coverage (0-1), drawn over under, in straight alpha like the TGA files."""
    alpha = color[3] / 255 * coverage
    below = under[3] / 255 * (1 - alpha)
    total = alpha + below
    if not total:
        return under
    rgb = tuple(round((c * alpha + u * below) / total) for c, u in zip(color[:3], under[:3]))
    return (*rgb, round(total * 255))


# The line along the bottom of a chat window's title bar: the row divider over the panel, solid.
TITLE_DIVIDER_RGBA = snapped(over(ROW_DIVIDER_RGBA, 1, PANEL_RGBA))


def rounded_rect_distance(x, y, left, top, right, bottom, radius):
    """Signed distance from (x, y) to a rounded rectangle's outline, negative inside."""
    qx = abs(x - (left + right) / 2) - ((right - left) / 2 - radius)
    qy = abs(y - (top + bottom) / 2) - ((bottom - top) / 2 - radius)
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - radius


def panel_texture(width, height, fill=PANEL_RGBA, edge=EDGE_FADED):
    """The overlay's panel: the body inside a rounded outline and a 1px edge along it.

    Drawn like EQ Triage's TriageWindow.paintEvent: the outline runs half a pixel in from the border,
    the body fills inside it and the edge is a 1px line centered on it, anti-aliased by supersampling.
    """
    panel = Texture(width, height)
    step = 1 / SUPERSAMPLE
    samples = SUPERSAMPLE * SUPERSAMPLE

    def distance(x, y):
        return rounded_rect_distance(x, y, 0.5, 0.5, width - 0.5, height - 0.5, CORNER_RADIUS)

    for y in range(height):
        for x in range(width):
            # Every point of a pixel is within 0.71 of its center, so pixels this far from the
            # outline are wholly inside or outside the body and clear of the edge.
            center = distance(x + 0.5, y + 0.5)
            if abs(center) > 1.25:
                inside, on_edge = (samples if center < 0 else 0), 0
            else:
                inside = on_edge = 0
                for j in range(SUPERSAMPLE):
                    sample_y = y + (j + 0.5) * step
                    for i in range(SUPERSAMPLE):
                        d = distance(x + (i + 0.5) * step, sample_y)
                        inside += d < 0
                        on_edge += abs(d) <= 0.5
            body = over(fill, inside / samples)
            panel.rows[y][x] = over(edge, on_edge / samples, body)
    return panel


def ellipse_distance(x, y, cx, cy, rx, ry):
    """Roughly how far (x, y) is from an ellipse's outline, in pixels."""
    return abs(math.hypot((x - cx) / rx, (y - cy) / ry) - 1) * min(rx, ry)


def segment_distance(x, y, start, end):
    (ax, ay), (bx, by) = start, end
    dx, dy = bx - ax, by - ay
    t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - ax - t * dx, y - ay - t * dy)


def ink(texture, width, height, inside, alpha=255):
    """Paints white where inside(x, y) holds into texture's top left width x height, anti-aliased by
    supersampling, and returns texture."""
    step = 1 / SUPERSAMPLE
    samples = SUPERSAMPLE * SUPERSAMPLE
    for py in range(height):
        for px in range(width):
            hits = sum(inside(px + (i + 0.5) * step, py + (j + 0.5) * step)
                       for j in range(SUPERSAMPLE) for i in range(SUPERSAMPLE))
            texture.rows[py][px] = (255, 255, 255, round(alpha * hits / samples))
    return texture


def clear_texture(width, height):
    # Clear white, so filtering at the ink's edges never darkens it.
    return Texture(width, height, (255, 255, 255, 0))


def percent_glyph():
    """The % sign at the top left of its own texture, white for FillTint to color. The rest of the
    texture is clear, so repeating it never shows a second %."""
    def inside(x, y):
        y -= PERCENT_SUBPIXEL
        distance = min(*(ellipse_distance(x, y, cx, cy, *PERCENT_RING_RADII) for cx, cy in PERCENT_RINGS),
                       segment_distance(x, y, *PERCENT_SLASH))
        return distance <= GLYPH_STROKE / 2

    return ink(clear_texture(BACKGROUND_SIZE, BACKGROUND_SIZE), PERCENT_WIDTH, PERCENT_GLYPH_HEIGHT, inside)


def chevron(up, alpha, height=SCROLL_BUTTON_HEIGHT):
    """A scrollbar arrow button: a small chevron in the middle of a clear SCROLL_WIDTH-wide piece, height tall (the
    dropdowns' is taller, see COMBO_ARROW_HEIGHT)."""
    middle, rise = height / 2, 1.25
    tip, arms = (middle - rise, middle + rise) if up else (middle + rise, middle - rise)
    center = SCROLL_WIDTH / 2
    points = ((center - 2.5, arms), (center, tip), (center + 2.5, arms))

    def inside(x, y):
        return min(segment_distance(x, y, points[0], points[1]),
                   segment_distance(x, y, points[1], points[2])) <= GLYPH_STROKE / 2

    return ink(clear_texture(SCROLL_WIDTH, height), SCROLL_WIDTH, height, inside, alpha)


def chat_close_art(alpha):
    """The chat windows' close box: an X drawn like the scrollbar's arrows in the middle of a clear square (see
    CHAT_CLOSE_SIZE)."""
    low, high = CHAT_CLOSE_SIZE / 2 - CHAT_CLOSE_REACH, CHAT_CLOSE_SIZE / 2 + CHAT_CLOSE_REACH

    def inside(x, y):
        return min(segment_distance(x, y, (low, low), (high, high)),
                   segment_distance(x, y, (low, high), (high, low))) <= GLYPH_STROKE / 2

    return ink(clear_texture(CHAT_CLOSE_SIZE, CHAT_CLOSE_SIZE), CHAT_CLOSE_SIZE, CHAT_CLOSE_SIZE, inside, alpha)


def thumb_pieces():
    """The scrollbar thumb: a THUMB_WIDTH pill centered in the scrollbar, cut into a rounded top, a 1px
    middle the client repeats, and a rounded bottom."""
    left = (SCROLL_WIDTH - THUMB_WIDTH) / 2
    height = 2 * THUMB_CAP + 1

    def inside(x, y):
        return rounded_rect_distance(x, y, left, 0, left + THUMB_WIDTH, height, THUMB_WIDTH / 2) < 0

    pill = ink(clear_texture(SCROLL_WIDTH, height), SCROLL_WIDTH, height, inside, THUMB_ALPHA)
    return {
        'ThumbTop': pill.crop(0, 0, SCROLL_WIDTH, THUMB_CAP),
        'ThumbMiddle': pill.crop(0, THUMB_CAP, SCROLL_WIDTH, 1),
        'ThumbBottom': pill.crop(0, THUMB_CAP + 1, SCROLL_WIDTH, THUMB_CAP),
    }


# The window selector's icons: line icons on a 16px grid, each a function giving the signed distance
# from a point to its ink (negative inside), built from strokes ICON_STROKE thick and a few filled shapes.

def stroke(distance):
    """A line's signed distance, from the distance to its middle."""
    return distance - ICON_STROKE / 2


def polyline_distance(x, y, points, closed=False):
    ends = list(points) + ([points[0]] if closed else [])
    return min(segment_distance(x, y, a, b) for a, b in zip(ends, ends[1:]))


def arc_distance(x, y, cx, cy, r, start, end):
    """Distance to a circle's arc running clockwise on screen from angle start to end, in degrees from
    the right (90 is straight down)."""
    angle = math.degrees(math.atan2(y - cy, x - cx))
    if (angle - start) % 360 <= (end - start) % 360 or end - start >= 360:
        return abs(math.hypot(x - cx, y - cy) - r)
    return min(math.hypot(x - cx - r * math.cos(math.radians(a)), y - cy - r * math.sin(math.radians(a)))
               for a in (start, end))


def ellipse_signed(x, y, cx, cy, rx, ry):
    """Roughly the signed distance to a filled ellipse."""
    return (math.hypot((x - cx) / rx, (y - cy) / ry) - 1) * min(rx, ry)


def four_point_star(cx, cy, tip, waist):
    """The corners of a four-pointed star: its tips tip from the middle, its waist corners waist across."""
    return [(cx, cy - tip), (cx + waist, cy - waist), (cx + tip, cy), (cx + waist, cy + waist),
            (cx, cy + tip), (cx - waist, cy + waist), (cx - tip, cy), (cx - waist, cy - waist)]


def actions_icon(x, y):
    # Two crossed swords, each a blade, a crossguard and a grip.
    return stroke(min(
        segment_distance(x, y, (2.5, 2.5), (11, 11)), segment_distance(x, y, (9.5, 12.5), (12.5, 9.5)),
        segment_distance(x, y, (11, 11), (13.5, 13.5)),
        segment_distance(x, y, (13.5, 2.5), (5, 11)), segment_distance(x, y, (3.5, 9.5), (6.5, 12.5)),
        segment_distance(x, y, (5, 11), (2.5, 13.5)),
    ))


def inventory_icon(x, y):
    # A backpack: its body, the loop on top and a pocket.
    loop = abs(rounded_rect_distance(x, y, 5.5, 1.75, 10.5, 7, 2)) if y < 5 else math.inf
    return stroke(min(
        abs(rounded_rect_distance(x, y, 2.75, 5, 13.25, 14.25, 3)), loop,
        polyline_distance(x, y, ((5.5, 14.25), (5.5, 10.5), (10.5, 10.5), (10.5, 14.25))),
    ))


def options_icon(x, y):
    # Three sliders, each a line with a round knob.
    lines = stroke(min(segment_distance(x, y, (1.75, row), (14.25, row)) for row in (3.5, 8, 12.5)))
    knobs = min(math.hypot(x - kx, y - ky) - 2.1 for kx, ky in ((10.5, 3.5), (5.5, 8), (9.5, 12.5)))
    return min(lines, knobs)


def friends_icon(x, y):
    # Two people: one in front, and the edge of one behind to the right.
    body = arc_distance(x, y, 6, 14.5, 4.5, 180, 360)
    behind_head = arc_distance(x, y, 10.75, 5, 2.4, -60, 90)
    behind_body = arc_distance(x, y, 11, 14.5, 3.75, 280, 360)
    return stroke(min(abs(math.hypot(x - 6, y - 4.75) - 2.5), body, behind_head, behind_body))


def hotbuttons_icon(x, y):
    # A 2x2 grid of hot buttons.
    return stroke(min(abs(rounded_rect_distance(x, y, left, top, left + 4, top + 4, 1))
                      for left in (2.5, 9.5) for top in (2.5, 9.5)))


def polygon_signed(x, y, points):
    """The signed distance to a filled polygon."""
    inside = False
    for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    distance = polyline_distance(x, y, points, closed=True)
    return -distance if inside else distance


def spells_icon(x, y):
    # A wand (the user's idea) with a solid four-pointed star at its tip, a small sparkle and a speck.
    lines = min(segment_distance(x, y, (2.25, 13.75), (9, 7)),
                segment_distance(x, y, (4.5, 2), (4.5, 5)), segment_distance(x, y, (3, 3.5), (6, 3.5)))
    return min(stroke(lines), polygon_signed(x, y, four_point_star(12, 4, 3.5, 1)) - 0.25,
               math.hypot(x - 13, y - 11) - 0.9)


def pet_icon(x, y):
    # A paw print, filled: four toes over a pad.
    toes = min(ellipse_signed(x, y, tx, ty, 1.55, 1.95) for tx, ty in ((2.9, 7), (6, 3.6), (10, 3.6), (13.1, 7)))
    return min(toes, ellipse_signed(x, y, 8, 11.25, 3.75, 3.1))


def effects_icon(x, y):
    # A four-pointed star with a small sparkle beside it, for the spells on you (the user moved it here
    # from Spells, which got the wand).
    sparkle = min(segment_distance(x, y, (13, 1.5), (13, 5.5)), segment_distance(x, y, (11, 3.5), (15, 3.5)))
    return stroke(min(polyline_distance(x, y, four_point_star(7, 9.25, 5.75, 1.4), closed=True), sparkle))


# The Actions window's icons: its four tabs, then the social page arrows.

def main_icon(x, y):
    # A house, for the page of everyday commands.
    return stroke(min(
        polyline_distance(x, y, ((1.75, 8.25), (8, 2.25), (14.25, 8.25))),
        polyline_distance(x, y, ((3.75, 6.5), (3.75, 13.75), (12.25, 13.75), (12.25, 6.5))),
        polyline_distance(x, y, ((6.75, 13.75), (6.75, 10), (9.25, 10), (9.25, 13.75))),
    ))


def abilities_icon(x, y):
    # A compass, for the general skills (Sense Heading, Tracking, Forage, Hide and the like): a ring and a
    # solid needle across it. The user asked for icons that fit the pages; a lightning bolt came first.
    needle = polygon_signed(x, y, [(11, 5), (9, 9), (5, 11), (7, 7)]) - 0.2
    return min(stroke(abs(math.hypot(x - 8, y - 8) - 6.5)), needle)


def combat_icon(x, y):
    # One sword, for auto attack and the combat skills (the selector's Actions icon crosses two): a solid blade
    # tapering to its tip, the crossguard, the grip and a round pommel. A shield came first; a line for a
    # blade looked like a pen.
    blade = polygon_signed(x, y, [(14, 2), (6.8, 10.6), (5.4, 9.2)]) - 0.3
    hilt = min(segment_distance(x, y, (3.5, 8.75), (7.25, 12.5)), segment_distance(x, y, (5.5, 10.5), (3, 13)))
    return min(blade, stroke(hilt), math.hypot(x - 2.4, y - 13.6) - 1.3)


def socials_icon(x, y):
    # A speech bubble with its tail at the bottom left, three dots of talk in it.
    bubble = abs(rounded_rect_distance(x, y, 1.75, 2.25, 14.25, 11, 2.5))
    tail = polyline_distance(x, y, ((4.5, 11), (3.75, 14.5), (8, 11)))
    dots = min(math.hypot(x - dx, y - 6.6) - 1 for dx in (5, 8, 11))
    return min(stroke(min(bubble, tail)), dots)


def left_icon(x, y):
    # The social page arrows: a small chevron, on the smaller arrow buttons.
    return stroke(polyline_distance(x, y, ((9.75, 4.5), (6.25, 8), (9.75, 11.5))))


def right_icon(x, y):
    return stroke(polyline_distance(x, y, ((6.25, 4.5), (9.75, 8), (6.25, 11.5))))


def minus_icon(x, y):
    # The AA window's XP-to-AA buttons: a minus and a plus, as wide as the page arrows are tall.
    return stroke(segment_distance(x, y, (4.5, 8), (11.5, 8)))


def plus_icon(x, y):
    return stroke(min(segment_distance(x, y, (4.5, 8), (11.5, 8)), segment_distance(x, y, (8, 4.5), (8, 11.5))))


def book_icon(x, y):
    # The spell bar's spellbook button: an open book, two pages meeting at the spine, their outer corners
    # raised a little as an open book's are.
    pages = [((8, 4.5), (1.75, 2.75), (1.75, 12.25), (8, 14)), ((8, 4.5), (14.25, 2.75), (14.25, 12.25), (8, 14))]
    return stroke(min(polyline_distance(x, y, page, closed=True) for page in pages))


ICONS = {'Actions': actions_icon, 'Inventory': inventory_icon, 'Options': options_icon,
         'Friends': friends_icon, 'Hotbuttons': hotbuttons_icon, 'Spells': spells_icon, 'Pet': pet_icon,
         'Effects': effects_icon,
         'Main': main_icon, 'Abilities': abilities_icon, 'Combat': combat_icon, 'Socials': socials_icon}
ARROW_ICONS = {'Left': left_icon, 'Right': right_icon}  # drawn on ARROW_SIZE buttons
SIGN_ICONS = {'Minus': minus_icon, 'Plus': plus_icon}  # the same


# The hot button window's empty slots: what goes in each (see HOT_SLOTS).

def primary_icon(x, y):
    # A longsword pointing up and right across the whole square: a solid straight blade with a pointed tip, a
    # wide crossguard, the grip and a round pommel. Drawn standing up, then turned 45 degrees. A blade tapering
    # from the guard, shorter, looked like a dagger in game (the user); standing up, like a cross.
    u, v = 8 + (x - 8 + y - 8) * math.sqrt(0.5), 8 + (y - 8 - (x - 8)) * math.sqrt(0.5)
    blade = polygon_signed(u, v, [(8, -2.6), (9.3, -1), (9.3, 9.6), (6.7, 9.6), (6.7, -1)])
    hilt = min(segment_distance(u, v, (3.6, 10.4), (12.4, 10.4)), segment_distance(u, v, (8, 10.6), (8, 13.4)))
    return min(blade, stroke(hilt), math.hypot(u - 8, v - 14.6) - 1.35)


def secondary_icon(x, y):
    # A heater shield, a flat top and straight sides curving down to a point, its left half filled as in
    # heraldry: the outline alone looked plain in game (the user); a cross, a boss or a round shield read less
    # clearly at 16px.
    right = [(13, 2.5), (13, 7.5), (12.4, 10.2), (10.6, 12.6)]
    left = [(ICON_SIZE - px, py) for px, py in right]
    outline = polyline_distance(x, y, [(8, 14.5)] + left[::-1] + right, closed=True)
    return min(stroke(outline), polygon_signed(x, y, [(8, 14.5)] + left[::-1] + [(8, 2.5)]))


def range_icon(x, y):
    # A bow drawn diagonally, the limb bulging up and left and the string straight across it, thinner, with an
    # arrow nocked on the string pointing up and left through the limb. A bow alone read as a crescent.
    limb = arc_distance(x, y, 12, 12, 9, 165, 285)
    string = segment_distance(x, y, (3.31, 14.33), (14.33, 3.31))
    shaft = segment_distance(x, y, (12.75, 12.75), (4.5, 4.5))
    head = polygon_signed(x, y, [(1.75, 1.75), (6.25, 3.25), (3.25, 6.25)]) - 0.2
    return min(stroke(min(limb, shaft)), head, string - 0.5)


def ammo_icon(x, y):
    # An arrow pointing up and right, corner to corner (the user asked for it longer): a small solid head, the
    # shaft and a V of fletching at each of two spots near the tail.
    head = polygon_signed(x, y, [(15.25, 0.75), (10.9, 2.1), (13.9, 5.1)]) - 0.2
    shaft = segment_distance(x, y, (1, 15), (12.5, 3.5))
    vanes = min(polyline_distance(x, y, ((0.9, 11.9), (3.1, 12.9), (4.1, 15.1))),
                polyline_distance(x, y, ((2.9, 9.9), (5.1, 10.9), (6.1, 13.1))))
    return min(head, stroke(min(shaft, vanes)))


# The inventory window's other worn slots (see INV_WORN), each what goes in it. The ear, neck and ring are drawn in
# lines like the weapons; the rest are solid shapes with their details cut in: in outline, they read poorly at the
# slot's size in its dim color (the user).

def carved(shape, *holes):
    """shape's signed distance with holes taken out of it."""
    return max(shape, *(-hole for hole in holes))


def slit(distance, half=0.45):
    """A thin cut half wide each side of a line, from the distance to the line."""
    return distance - half


def turned(x, y, degrees, cx=8, cy=8):
    """(x, y) turned about (cx, cy) by degrees, to draw a shape tilted by that much the other way."""
    a = math.radians(degrees)
    dx, dy = x - cx, y - cy
    return cx + dx * math.cos(a) + dy * math.sin(a), cy - dx * math.sin(a) + dy * math.cos(a)


def ear_icon(x, y):
    # A right ear from the side: the rim arching over and down the back to the lobe, the lobe's curve up to the
    # front, and the fold inside.
    rim = min(arc_distance(x, y, 8, 6.5, 5.25, 200, 45), segment_distance(x, y, (11.71, 10.21), (10.1, 13.2)),
              arc_distance(x, y, 8.4, 13, 1.75, 0, 180), segment_distance(x, y, (6.65, 13), (6.4, 11)))
    fold = min(arc_distance(x, y, 8.1, 6.9, 2.3, 190, 40), segment_distance(x, y, (9.86, 8.38), (8.6, 10.5)))
    return stroke(min(rim, fold))


def head_icon(x, y):
    # A helm: a dome down to straight cheeks, with a T of eye slit and nose slit cut through it.
    helm = min(math.hypot(x - 8, y - 7.5) - 6, rounded_rect_distance(x, y, 2, 7.5, 14, 14.75, 0.75))
    slits = min(rounded_rect_distance(x, y, 3.75, 7.75, 12.25, 9.25, 0.5),
                rounded_rect_distance(x, y, 7.25, 8.5, 8.75, 13, 0.5))
    return carved(helm, slits)


def face_icon(x, y):
    # A full mask: an oval face narrowing to the chin, the eyes and the mouth cut out. A mask over the eyes alone read
    # as an infinity sign.
    face = min(ellipse_signed(x, y, 8, 7, 5.5, 6), polygon_signed(x, y, [(3, 9), (13, 9), (8, 15)]))
    eyes = min(ellipse_signed(x, y, ex, 6.75, 1.75, 1) for ex in (5.5, 10.5))
    return carved(face, eyes, ellipse_signed(x, y, 8, 11.25, 1.75, 0.6))


def neck_icon(x, y):
    # A necklace: the chain hanging in a curve, and a solid pendant under its lowest point.
    chain = arc_distance(x, y, 8, 2.5, 6.25, 10, 170)
    pendant = polygon_signed(x, y, [(8, 9.75), (10, 12.25), (8, 14.75), (6, 12.25)]) - 0.2
    return min(stroke(chain), pendant)


def shoulders_icon(x, y):
    # A pauldron from the side, tilted down to the right as it sits on the shoulder: a domed shell and two plates
    # stepping down and out from under it, each past a gap. Upright, a dome over plates read as a burger, a rainbow or
    # a mushroom; spiked, as a crown; a pair on a collar, as a moustache.
    u, v = turned(x, y, 22)
    shell = max(ellipse_signed(u, v, 7.5, 8.5, 6.25, 5.5), v - 8.5)
    plate = max(ellipse_signed(u, v, 7.5, 8.9, 7.25, 3.25), -(v - 8.9))
    lower = max(ellipse_signed(u, v, 7.5, 12.2, 6.25, 2.75), -(v - 12.2))
    return min(shell, carved(plate, shell - 0.9), carved(lower, plate - 0.9, shell - 0.9))


def arms_icon(x, y):
    # An arm flexed at the elbow: the upper arm with the biceps bulging over it, the forearm rising to a fist, and the
    # elbow's crease, the cuff and the fingers cut in. An arm bent at the elbow in outline read as a pipe.
    arm = polygon_signed(x, y, [(0.75, 14.5), (0.75, 11), (2.75, 9), (5.25, 7.75), (7.75, 8.25), (9.25, 9.5),
                                (9.75, 6.25), (9.25, 5), (9.25, 1.75), (11.75, 0.75), (14.25, 1.25), (14.75, 4),
                                (13.5, 5.25), (13.25, 6.5), (14, 10.75), (12.75, 13.5), (10, 14.5)]) - 0.2
    crease = slit(segment_distance(x, y, (9.25, 9.5), (10.25, 11.5)), 0.4)
    fingers = min(slit(segment_distance(x, y, (8.75, fy), (11.5, fy)), 0.4) for fy in (2.5, 4))
    cuff = slit(abs(y - 6.25)) if x > 9.5 else math.inf
    return carved(arm, crease, fingers, cuff)


def back_icon(x, y):
    # A cloak: hanging from a narrow collar and flaring to the hem, two folds and a round clasp cut into it. Rounded
    # over the shoulders, it read as a bell.
    cloak = polygon_signed(x, y, [(5.5, 1.5), (10.5, 1.5), (14.25, 14.5), (1.75, 14.5)])
    folds = min(slit(segment_distance(x, y, top, bottom)) for top, bottom in (((6.75, 5.25), (5.5, 15)),
                                                                             ((9.25, 5.25), (10.5, 15))))
    clasp = slit(abs(math.hypot(x - 8, y - 3.25) - 1.1), 0.4)
    return carved(cloak, folds, clasp)


def wrist_icon(x, y):
    # A bracer standing up, wider at the elbow end, bands cut off at both ends and a zigzag of lacing cut down its
    # middle. A band in outline read as a stack of coins; a tube on the diagonal, as a battery.
    width = 4.75 - (y - 1) / 14 * 1.5
    body = max(abs(x - 8) - width, abs(y - 8) - 7) - 0.25
    bands = min(slit(abs(y - h)) for h in (3.25, 12.75))
    lacing = min(slit(segment_distance(x, y, (x0, a), (x1, a + 1.75)), 0.4)
                 for a in (4.75, 7.25, 9.75) for x0, x1 in ((6.75, 9.25), (9.25, 6.75)))
    return carved(body, bands, lacing)


def hands_icon(x, y):
    # A glove: four fingers with gaps between them, the thumb out to the left, and the cuff under a cut.
    hand = min(rounded_rect_distance(x, y, 4.75, 1.25, 12.25, 11.5, 1.75),
               segment_distance(x, y, (5.25, 9.25), (2, 5.75)) - 1.2)
    fingers = min(slit(segment_distance(x, y, (fx, 0), (fx, 6)), 0.4) for fx in (6.6, 8.5, 10.4))
    return min(carved(hand, fingers), rounded_rect_distance(x, y, 5, 12.25, 12, 15, 0.5))


def fingers_icon(x, y):
    # A ring: the band, and a solid stone set on top of it.
    stone = polygon_signed(x, y, [(8, 1.25), (10.5, 3.75), (8, 6.25), (5.5, 3.75)]) - 0.2
    return min(stroke(abs(math.hypot(x - 8, y - 10.25) - 4.5)), stone)


def chest_icon(x, y):
    # A tunic of armor: shoulders and short sleeves, narrowing to the waist, a V at the neck and a belt line cut in.
    body = polygon_signed(x, y, [(5.5, 1.5), (1.75, 3.25), (0.75, 7.75), (3.5, 8.25), (3.75, 14.5), (12.25, 14.5),
                                 (12.5, 8.25), (15.25, 7.75), (14.25, 3.25), (10.5, 1.5)])
    neck = polygon_signed(x, y, [(5.25, 0.5), (10.75, 0.5), (8, 5.25)])
    return carved(body, neck, slit(abs(y - 11.25)))


def legs_icon(x, y):
    # Leggings: the waistband with a cut under it, and both legs down to their cuffs, the gap between them.
    legs = polygon_signed(x, y, [(3.25, 1.5), (12.75, 1.5), (14, 14.75), (9.25, 14.75), (8, 6.5), (6.75, 14.75),
                                 (2, 14.75)])
    return carved(legs, slit(abs(y - 4)))


def feet_icon(x, y):
    # A boot from the side, toe to the right: the shaft with its cuff cut off, the foot and the sole under a cut.
    boot = polygon_signed(x, y, [(4.25, 1.25), (10.25, 1.25), (10.25, 8), (13.5, 9.5), (15, 11.75), (15, 14.75),
                                 (3, 14.75), (3.5, 8)])
    return carved(boot, slit(abs(y - 4)), slit(abs(y - 12.75)))


def waist_icon(x, y):
    # A belt: the strap across with its pointed end on the right and two holes in it, and a square buckle over it, its
    # frame and prong solid and the strap seen through it past a gap. Cut apart from the buckle, the strap read as
    # separate blocks.
    strap = polygon_signed(x, y, [(0.5, 6), (13.5, 6), (15.5, 8), (13.5, 10), (0.5, 10)])
    outer = rounded_rect_distance(x, y, 3.25, 3.5, 9.75, 12.5, 1.25)
    inner = rounded_rect_distance(x, y, 5, 5.25, 8, 10.75, 0.5)
    holes = min(math.hypot(x - hx, y - 8) - 0.7 for hx in (11.25, 13.25))
    seen = carved(strap, slit(abs(inner), 0.4), holes)
    return min(seen, carved(outer, inner), segment_distance(x, y, (4, 8), (9, 8)) - 0.5)


SLOT_ICONS = {'Primary': primary_icon, 'Secondary': secondary_icon, 'Range': range_icon, 'Ammo': ammo_icon,
              'Ear': ear_icon, 'Head': head_icon, 'Face': face_icon, 'Neck': neck_icon, 'Shoulders': shoulders_icon,
              'Arms': arms_icon, 'Back': back_icon, 'Wrist': wrist_icon, 'Hands': hands_icon, 'Fingers': fingers_icon,
              'Chest': chest_icon, 'Legs': legs_icon, 'Feet': feet_icon, 'Waist': waist_icon}
# They're drawn big, strokes and all: each icon's ink fills a box SLOT_ICON_SHARE of the slot's side at its
# longer side, centered on the slot, so the sword and arrow, running corner to corner, take about that much of
# its diagonal. The user asked for about 75% of the diagonal for all four; by the diagonal alone, the upright
# shield would outgrow the slot.
SLOT_ICON_SHARE = 0.75
# In the row dividers' color (the group and effects windows') as it shows over the panel: the user wanted the
# icons more subdued.
SLOT_ICON_RGBA = snapped(over(ROW_DIVIDER_RGBA, 1, PANEL_RGBA))
INK_STEP = 1 / 8  # how finely ink_box() looks for an icon's ink


def ink_box(shape):
    """The box (left, top, right, bottom) around shape's ink, to INK_STEP, on its ICON_SIZE grid and a margin."""
    steps = [i * INK_STEP for i in range(round(-2 / INK_STEP), round((ICON_SIZE + 2) / INK_STEP) + 1)]
    ink = [(x, y) for y in steps for x in steps if shape(x, y) < 0]
    return (min(x for x, _ in ink), min(y for _, y in ink), max(x for x, _ in ink), max(y for _, y in ink))


def slot_icon_coverage(shape):
    """shape's coverage on a HOT_SIZE grid, scaled up so its ink's box is SLOT_ICON_SHARE of the slot at its
    longer side, and centered on it."""
    left, top, right, bottom = ink_box(shape)
    scale = SLOT_ICON_SHARE * HOT_SIZE / max(right - left, bottom - top)
    middle_x, middle_y, half = (left + right) / 2, (top + bottom) / 2, HOT_SIZE / 2
    return icon_coverage(
        lambda x, y: shape(middle_x + (x - half) / scale, middle_y + (y - half) / scale) * scale, HOT_SIZE)


def icon_coverage(shape, size=ICON_SIZE):
    """How much of each pixel of the size-square grid shape inks, 0 to 1, rows top first. Only pixels near
    the ink's edge are supersampled."""
    step = 1 / SUPERSAMPLE
    rows = []
    for py in range(size):
        row = []
        for px in range(size):
            center = shape(px + 0.5, py + 0.5)
            if abs(center) > 1.5:
                row.append(1.0 if center < 0 else 0.0)
            else:
                row.append(sum(shape(px + (i + 0.5) * step, py + (j + 0.5) * step) < 0
                               for j in range(SUPERSAMPLE) for i in range(SUPERSAMPLE)) / SUPERSAMPLE ** 2)
        rows.append(row)
    return rows


def toggle_art(coverage, state, size=TOGGLE_SIZE, height=None):
    """An icon button in one state, like a selector toggle: a button of ICON_LOOKS' colors, size wide and
    height tall (square without one), with the icon centered on it, every pixel snapped()."""
    height = height or size
    fill, edge, icon_alpha = ICON_LOOKS[state]
    art = panel_texture(size, height, fill, edge)
    left, top = (size - ICON_SIZE) // 2, (height - ICON_SIZE) // 2
    for y, row in enumerate(coverage):
        for x, amount in enumerate(row):
            if amount:
                under = art.rows[top + y][left + x]
                art.rows[top + y][left + x] = over((*ICON_RGB, icon_alpha), amount, under)
    return snapped_art(art)


def tab_art(coverage, state, width, name=None):
    """An Actions window tab, width wide: the icon's toggle in one state at the top of TAB_ART_HEIGHT of clear,
    or TAB_SHIFT lower for an open page's tab (Pressed), since the client draws the others that much lower. With name,
    an AA or friends window tab: no icon, and the page's name painted on in the icon's color and brightness (see
    TAB_INK)."""
    toggle = toggle_art(coverage, state, width, TOGGLE_SIZE)
    if name:
        at, name_ink = TAB_INK[name]
        toggle = snapped_art(painted(toggle, name_ink, at, (*ICON_RGB, ICON_LOOKS[state][2])))
    art = Texture(width, TAB_ART_HEIGHT)
    art.paste(toggle, 0, TAB_SHIFT if state == 'Pressed' else 0)
    return art


def swatch_art(rgb, state):
    """A tracking filter in one state (see FILTER_SWATCH): a selector toggle's look, FILTER_SIZE square, with a
    rounded square of rgb in its middle at SWATCH_ALPHA's, every pixel snapped()."""
    fill, edge, _ = TOGGLE_LOOKS[state]
    art = panel_texture(FILTER_SIZE, FILTER_SIZE, fill, edge)
    low = (FILTER_SIZE - FILTER_SWATCH) / 2
    high = low + FILTER_SWATCH
    coverage = icon_coverage(lambda x, y: rounded_rect_distance(x, y, low, low, high, high, SWATCH_RADIUS),
                             FILTER_SIZE)
    for y, row in enumerate(coverage):
        for x, amount in enumerate(row):
            if amount:
                art.rows[y][x] = over((*rgb, SWATCH_ALPHA[state]), amount, art.rows[y][x])
    return snapped_art(art)


def slot_icon_art(shape):
    """An empty item slot in the hot button window: the macros' plain button with shape's icon on it, big and
    in the dividers' color (see SLOT_ICON_SHARE), solid()."""
    art = labeled_button_art(HOT_SIZE, HOT_SIZE, '', 'Normal')
    for y, row in enumerate(slot_icon_coverage(shape)):
        for x, amount in enumerate(row):
            if amount:
                art.rows[y][x] = over(SLOT_ICON_RGBA, amount, art.rows[y][x])
    return solid(art)


def frame_pieces():
    """The window frame's eight pieces, cut from a panel just big enough to hold every corner."""
    size = 2 * BORDER + 1
    panel = panel_texture(size, size)
    far = BORDER + 1

    def corner(x, y):
        return panel.crop(x, y, BORDER, BORDER)

    def across(y):
        return panel.crop(BORDER, y, 1, BORDER).repeated(PIECE_LENGTH, BORDER)

    def down(x):
        return panel.crop(x, BORDER, BORDER, 1).repeated(BORDER, PIECE_LENGTH)

    return {
        'FrameTopLeft': corner(0, 0), 'FrameTop': across(0), 'FrameTopRight': corner(far, 0),
        'FrameLeft': down(0), 'FrameRight': down(far),
        'FrameBottomLeft': corner(0, far), 'FrameBottom': across(far), 'FrameBottomRight': corner(far, far),
    }


def snapped_art(texture):
    """texture with every pixel snapped(). Snapping only the colors isn't enough: where a shape's edge
    blends (the buttons' 1px edge over the half-covered fill came out at alpha 58), pixels fall between
    steps, and the buttons' edges showed a pattern in game."""
    texture.rows = [[snapped(pixel) for pixel in row] for row in texture.rows]
    return texture


def solid(texture):
    """texture over the panel's color, every pixel snapped(): opaque everywhere, rounded corners too, so the client
    can't ignore a click on a see-through spot (see HELPFUL_RGBA). On the opaque panel it looks the same."""
    texture.rows = [[snapped(over(pixel, 1, PANEL_RGBA)) for pixel in row] for row in texture.rows]
    return texture


def stepped(rgba, steps):
    """rgba's color that many of those steps lighter (or darker, when negative), keeping its alpha."""
    return (*(min(max(c + STEP * steps, 0), 255) for c in rgba[:3]), rgba[3])


def button_look(style, state):
    """A button's (fill, edge) in one state: the wash's own, or a solid style lightened when hovered,
    darkened when pressed and faded when disabled. Every color is snapped(), so none gets dithered."""
    fill, edge, _ = BUTTON_STYLES[style]
    if style == 'Wash':
        fill, edge = BUTTON_LOOKS[state]
    elif state == 'Flyby':
        fill = stepped(fill, BUTTON_HOVER_STEPS)
    elif state == 'Pressed':
        fill = stepped(fill, -BUTTON_PRESS_STEPS)
    elif state == 'Disabled':
        fill, edge = (*fill[:3], round(fill[3] * 0.45)), (*edge[:3], round(edge[3] * 0.45))
    return snapped(fill), snapped(edge)


def lettering(text):
    """text in LABEL_GLYPHS, LETTER_SPACING apart: its width, and its ink as (x, y) from its top left."""
    x, ink = 0, []
    for letter in text:
        rows = LABEL_GLYPHS[letter]
        ink += [(x + i, y) for y, row in enumerate(rows) for i, c in enumerate(row) if c == '#']
        x += len(rows[0]) + LETTER_SPACING
    return x - LETTER_SPACING, ink


def labeled_button_art(width, height, label, state, style=BUTTON_STYLE):
    """A button in one state with its label drawn on it in the style's text color, centered. The label's x-height is
    on the button's middle (LABEL_TOP down on a button BUTTON_HEIGHT tall)."""
    art = panel_texture(width, height, *button_look(style, state))
    text_width, ink = lettering(label)
    left = (width - text_width) // 2
    top = (height - LABEL_HEIGHT) // 2
    color = (*BUTTON_STYLES[style][2], LABEL_ALPHA[state])
    for x, y in ink:
        art.rows[top + y][left + x] = over(color, 1, art.rows[top + y][left + x])
    return snapped_art(art)


def harmful_row():
    """A harmful effect's row: clear like a helpful one, with a red bar on each side of the icon (see
    HARMFUL_RGBA)."""
    row = Texture(SLOT_WIDTH, ROW_HEIGHT, CLEAR)
    for bar_x in HARMFUL_BARS:
        left = bar_x - SLOT_X  # within the slot
        for y in range(ROW_ICON_MARGIN, ROW_ICON_MARGIN + ROW_ICON):
            row.rows[y][left:left + HARMFUL_BAR_WIDTH] = [HARMFUL_RGBA] * HARMFUL_BAR_WIDTH
    return row


def slider_track(width):
    """A stretch of the slider's track (see SLIDER_TEMPLATE): the bars' faint track as a line across the middle of the
    knob's height, clear above and below."""
    track = clear_texture(width, SLIDER_HEIGHT)
    for y in range(SLIDER_TRACK_TOP, SLIDER_TRACK_TOP + TWIN_BAR_HEIGHT):
        track.rows[y] = [EDGE_FADED] * width
    return track


def field_art(width, height):
    """The field template's look (FIELD_TEMPLATE: TUI_FieldEdge on every side and corner around FIELD_TEXTURE) as one
    piece, width by height, for a tab page, which can't hold the strip's Screen (see friends_window())."""
    field = Texture(width, height, FIELD_RGBA)
    field.rows[0] = [EDGE_FADED] * width
    field.rows[-1] = [EDGE_FADED] * width
    for row in field.rows:
        row[0] = row[-1] = EDGE_FADED
    return field


def title_piece(height=TITLE_HEIGHT, width=TITLE_PIECE_WIDTH):
    """A title bar: the panel's color with a row divider along its bottom, height tall (a chat window's
    TITLE_HEIGHT unless given). The one piece serves as the bar's left, middle and right, repeated across."""
    piece = Texture(width, height, PANEL_RGBA)
    piece.rows[-1] = [TITLE_DIVIDER_RGBA] * width
    return piece


def painted(texture, ink, at, color):
    """texture with ink (rows of hex digits, a pixel's coverage each, 0 to f) painted on in color, its top left at."""
    left, top = at
    for y, row in enumerate(ink):
        for x, digit in enumerate(row):
            pixel = texture.rows[top + y][left + x]
            texture.rows[top + y][left + x] = over(color, int(digit, 16) / 15, pixel)
    return texture


def quantity_title_piece():
    """The quantity window's title bar's left piece: the item window's bar reaching past the window's name, which is
    painted on in the text's color (see QUANTITY_TITLE_INK)."""
    left, top = QUANTITY_TITLE_INK_AT
    piece = title_piece(ITEM_TITLE_HEIGHT, left + len(QUANTITY_TITLE_INK[0]))
    return snapped_art(painted(piece, QUANTITY_TITLE_INK, QUANTITY_TITLE_INK_AT, (*TEXT_RGB, 255)))


def close_box_art(state):
    """The item and quantity windows' close box in one state: the Close button under CLOSE_CLEAR clear rows, the
    dialogs' plain wash with its name painted on in the text's color (see CLOSE_INK)."""
    button = painted(labeled_button_art(CLOSE_WIDTH, TEXT_BUTTON_HEIGHT, '', state), CLOSE_INK, CLOSE_INK_AT,
                     (*TEXT_RGB, LABEL_ALPHA[state]))
    art = clear_texture(CLOSE_WIDTH, CLOSE_CLEAR + TEXT_BUTTON_HEIGHT)
    art.rows[CLOSE_CLEAR:] = snapped_art(button).rows
    return art


def compass_mark_center(degrees):
    """Where a heading falls across the compass strip, from its left edge, a pixel column's middle being its index + 0.5
    (see COMPASS_FILE)."""
    return (COMPASS_NORTH_X + 0.5 + degrees * COMPASS_STRIP_WIDTH / 360) % COMPASS_STRIP_WIDTH


def compass_strip():
    """The compass's strip, the inside's height, clear but for its marks: a faint tick every 10° along the bottom of the
    tick row, a taller one in the text's color under N, E, S and W, and each direction's label centered over its
    heading (see COMPASS_MARKS). The game draws two copies end to end, so the ticks keep their spacing across the ends."""
    strip = clear_texture(COMPASS_STRIP_WIDTH, COMPASS_INSIDE_HEIGHT)
    ticks_bottom = COMPASS_TICKS_TOP + COMPASS_TICKS_HEIGHT
    for x in range(COMPASS_NORTH_X % COMPASS_TICK_STEP, COMPASS_STRIP_WIDTH, COMPASS_TICK_STEP):
        for y in range(ticks_bottom - COMPASS_TICK_HEIGHT, ticks_bottom):
            strip.rows[y][x] = EDGE_FADED
    for label, degrees, rgb in COMPASS_MARKS:
        center = compass_mark_center(degrees)
        width, ink = lettering(label)
        left = int(center - width / 2)  # exact: see COMPASS_MARKS
        for x, y in ink:
            strip.rows[COMPASS_LETTERS_TOP + y][left + x] = (*rgb, 255)
        if len(label) == 1:
            for y in range(COMPASS_TICKS_TOP, ticks_bottom):
                strip.rows[y][int(center)] = (*TEXT_RGB, 255)
    return strip


def compass_overlay():
    """What the compass draws over its strip, the inside's size: the panel's color over the strip within the window's
    padding each side, fading to clear over COMPASS_FADE more, and the soft red pointer line through the tick row at
    COMPASS_POINTER_X. Clear elsewhere, in the panel's color like the fade, so filtering never lightens its end."""
    overlay = Texture(COMPASS_INSIDE_WIDTH, COMPASS_INSIDE_HEIGHT, CLEAR)
    for i in range(LEFT + COMPASS_FADE):
        alpha = 255 if i < LEFT else round(255 * (LEFT + COMPASS_FADE - i) / (COMPASS_FADE + 1))
        for row in overlay.rows:
            row[i] = row[-1 - i] = (*PANEL_RGBA[:3], alpha)
    for y in range(COMPASS_TICKS_TOP, COMPASS_TICKS_TOP + COMPASS_TICKS_HEIGHT):
        overlay.rows[y][COMPASS_POINTER_X] = (*COMPASS_NORTH_RGB, 255)
    return overlay


def pieces():
    """Every piece of art the windows use, by name.

    The client draws a gauge's track and fill at their own size instead of stretching them (Infiniti-Blue
    sizes its A_GaugeFill to each gauge for the same reason), so they are exactly as big as their bar.
    The track is the edge color, like the overlay's border; fills are white for FillTint to color, softened
    to BAR_FILL's alpha, except the group window's and the mana bar's (solid, each exactly its names' color)
    and the server tick's (solid, with no track behind it).
    """
    # Each icon's (coverage, button width, button height).
    icons = {name: (icon_coverage(shape), TOGGLE_SIZE, TOGGLE_SIZE) for name, shape in ICONS.items()}
    icons.update({name: (icon_coverage(shape), ARROW_SIZE, ARROW_SIZE)
                  for name, shape in {**ARROW_ICONS, **SIGN_ICONS}.items()})
    icons['Book'] = (icon_coverage(book_icon), BOOK_WIDTH, TOGGLE_SIZE)  # the spell bar's wide book button
    return {
        **frame_pieces(),
        'TwinTrack': Texture(TWIN_BAR_WIDTH, TWIN_BAR_HEIGHT, EDGE_FADED),
        'TwinFill': Texture(TWIN_BAR_WIDTH, TWIN_BAR_HEIGHT, BAR_FILL),
        'CastTrack': Texture(CAST_BAR_WIDTH, TWIN_BAR_HEIGHT, EDGE_FADED),
        'CastFill': Texture(CAST_BAR_WIDTH, TWIN_BAR_HEIGHT, BAR_FILL),
        'PIWTrack': Texture(PIW_BAR_WIDTH, TWIN_BAR_HEIGHT, EDGE_FADED),
        'PIWFill': Texture(PIW_BAR_WIDTH, TWIN_BAR_HEIGHT, BAR_FILL),
        'MemberGaugeFill': Texture(GROUP_BAR_WIDTH, PET_BAR_HEIGHT, WHITE),
        'PetGaugeFill': Texture(GROUP_BAR_WIDTH - PET_INDENT, PET_BAR_HEIGHT, WHITE),
        'PlayerTrack': Texture(PLAYER_CONTENT_WIDTH, BAR_HEIGHT, EDGE_FADED),
        'PlayerFill': Texture(PLAYER_CONTENT_WIDTH, BAR_HEIGHT, BAR_FILL),
        'PlayerSolidFill': Texture(PLAYER_CONTENT_WIDTH, BAR_HEIGHT, WHITE),
        'TickFill': Texture(PLAYER_CONTENT_WIDTH, TICK_HEIGHT, WHITE),
        'InvTrack': Texture(INV_MIDDLE_WIDTH, BAR_HEIGHT, EDGE_FADED),  # the inventory's XP and AA bars
        'InvFill': Texture(INV_MIDDLE_WIDTH, BAR_HEIGHT, WHITE),  # solid (see GOLD_RGB)
        **{button_art(width, height, label, state): labeled_button_art(width, height, label, state)
           for (width, height), labels in BUTTON_LABELS.items() for label in labels for state in BUTTON_LOOKS},
        **{f'Scroll{way}{state}': chevron(way == 'Up', alpha)
           for way in ('Up', 'Down') for state, alpha in SCROLL_LOOKS.items()},
        **{f'ChatClose{state}': chat_close_art(alpha) for state, alpha in SCROLL_LOOKS.items()},
        **thumb_pieces(),
        **{f'Toggle{name}{state}': toggle_art(coverage, state, width, height)
           for name, (coverage, width, height) in icons.items() for state in ICON_LOOKS},
        'RowDivider': Texture(SLOT_WIDTH, 1, ROW_DIVIDER_RGBA),  # the effect slots' width
        'GroupDivider': Texture(GROUP_CONTENT_WIDTH, 1, ROW_DIVIDER_RGBA),  # the same, the group window's width
        'ActionsDivider': Texture(ACTIONS_CONTENT_WIDTH, 1, ROW_DIVIDER_RGBA),  # the same, the Actions window's width
        'MerchantDivider': Texture(MERCHANT_CONTENT_WIDTH, 1, ROW_DIVIDER_RGBA),  # the same, the merchant window's
        'GiveDivider': Texture(GIVE_CONTENT_WIDTH, 1, ROW_DIVIDER_RGBA),  # the same, the give window's
        'InvDivider': Texture(INV_COLUMN_WIDTH, 1, ROW_DIVIDER_RGBA),  # the same, the inventory's column's
        'TradeDivider': Texture(TRADE_CONTENT_WIDTH, 1, ROW_DIVIDER_RGBA),  # the same, the trade window's
        'HelpfulRow': Texture(SLOT_WIDTH, ROW_HEIGHT, HELPFUL_RGBA),
        'HarmfulRow': harmful_row(),
        'GemSlot': clear_texture(GEM_ROW_WIDTH, GEM_ROW_HEIGHT),  # a spell gem's row, clear (see spell_gem())
        'SpellBarDivider': Texture(SPELL_BAR_CONTENT_WIDTH, 1, ROW_DIVIDER_RGBA),  # the row divider, this window's width
        'RecastFill': Texture(RECAST_WIDTH, TICK_HEIGHT, BAR_FILL),
        'CastRecoveryFill': Texture(SPELL_BAR_CONTENT_WIDTH, TICK_HEIGHT, BAR_FILL),
        # The spell book's (see SPELLBOOK_FILE): a spell's slot, clear like a gem's, the row divider at a page's width
        # and across both pages, and the memorizing bar across the window.
        'BookSlot': clear_texture(BOOK_SLOT_WIDTH, BOOK_SLOT_HEIGHT),
        'BookRowDivider': Texture(BOOK_PAGE_WIDTH, 1, ROW_DIVIDER_RGBA),
        'BookDivider': Texture(BOOK_CONTENT_WIDTH, 1, ROW_DIVIDER_RGBA),
        'MemorizeFill': Texture(BOOK_CONTENT_WIDTH, TICK_HEIGHT, BAR_FILL),
        # The hot button window's, all solid (see HOTBUTTON_FILE): the macros' button, whose Normal is also an
        # item's or a spell's hot button under its icon, each empty slot with its icon, and the page arrows, as
        # wide as the Actions window's and a row tall.
        **{f'HotButton{state}': solid(labeled_button_art(HOT_SIZE, HOT_SIZE, '', state)) for state in BUTTON_LOOKS},
        **{f'HotSlot{name}': slot_icon_art(shape) for name, shape in SLOT_ICONS.items()},
        **{f'ToggleHot{name}{state}': solid(toggle_art(icons[name][0], state, ARROW_SIZE, HOT_SIZE))
           for name in ARROW_ICONS for state in ICON_LOOKS},
        # The quantity window's slider (see SLIDER_TEMPLATE): the knob in the buttons' looks, solid so the track
        # doesn't show through it, and the track on the background and the right end cap.
        **{f'SliderKnob{state}': solid(labeled_button_art(SLIDER_KNOB_WIDTH, SLIDER_HEIGHT, '', state))
           for state in BUTTON_LOOKS},
        'SliderTrack': slider_track(QUANTITY_CONTENT_WIDTH - SLIDER_KNOB_WIDTH),
        'SliderCapRight': slider_track(SLIDER_KNOB_WIDTH),
        # The coin boxes (see COIN_CAPTIONS), solid like the slots, so a drop anywhere on one counts.
        **{f'Coin{state}': solid(labeled_button_art(COIN_WIDTH, COIN_HEIGHT, '', state)) for state in BUTTON_LOOKS},
        **{f'BankCoin{state}': solid(labeled_button_art(BANK_COIN_WIDTH, COIN_HEIGHT, '', state))
           for state in BUTTON_LOOKS},
        'TitleBar': title_piece(),
        'ItemTitleBar': title_piece(ITEM_TITLE_HEIGHT),
        'QuantityTitle': quantity_title_piece(),
        **{f'ItemClose{state}': close_box_art(state) for state in BUTTON_LOOKS},
        'ListHeaderWash': Texture(PIECE_LENGTH, RAID_HEADER_HEIGHT, HEADER_RGBA),  # see LIST_HEADER
        'FieldEdge': Texture(1, 1, EDGE_FADED),
        'Clear': clear_texture(1, 1),
        'ClassAnim': clear_texture(1, 1),  # the inventory's class picture's own (see inventory_window())
        # The Actions window's tabs, and its tab and page border templates' clear pieces (see TAB_BORDER).
        **{f'Tab{icon}{state}': tab_art(icons[icon][0], state, width)
           for (*_, icon), width in zip(ACTIONS_PAGES, TAB_WIDTHS) for state in ('Normal', 'Pressed')},
        **{f'TabBorder{side}': clear_texture(*size) for side, size in TAB_BORDER_PIECES.items()},
        **{f'PageBorder{side}': clear_texture(*size) for side, size in PAGE_BORDER_PIECES.items()},
        **{f'ListPageBorder{side}': clear_texture(*size) for side, size in LIST_PAGE_BORDER_PIECES.items()},
        # The AA window's tabs, their names on them, and the row divider at its list's width (see AA_FILE).
        **{f'Tab{art}{state}': tab_art((), state, width, name)
           for (_, _, name, art), width in zip(AA_PAGES, AA_TAB_WIDTHS) for state in ('Normal', 'Pressed')},
        'AADivider': Texture(AA_LIST_WIDTH, 1, ROW_DIVIDER_RGBA),
        # The friends window's tabs, their names on them, and its name fields' strip (see FRIENDS_FILE).
        **{f'Tab{name}{state}': tab_art((), state, width, name)
           for (_, name, *_), width in zip(FRIENDS_PAGES, FRIENDS_TAB_WIDTHS) for state in ('Normal', 'Pressed')},
        'FriendsField': field_art(FRIENDS_FIELD_WIDTH, INPUT_HEIGHT),
        # The compass's strip, which the game slides, and what it draws over it (see COMPASS_FILE).
        'CompassStrip': compass_strip(),
        'CompassOverlay': compass_overlay(),
        # The tracking window's (see TRACKING_FILE): each filter in each toggle state, and the dropdowns' arrow, the
        # scrollbar's down chevron in the middle of the box's inside height.
        **{f'Filter{color_name}{state}': swatch_art(rgb, state)
           for _, color_name, _, rgb in TRACK_FILTERS for state in TOGGLE_LOOKS},
        **{f'ComboDown{state}': chevron(False, alpha, COMBO_ARROW_HEIGHT) for state, alpha in SCROLL_LOOKS.items()},
    }


def extruded(piece):
    """piece with a 1px margin repeating its outer pixels, so filtering never picks up a neighbour."""
    width, height = piece.width + 2, piece.height + 2
    margin = Texture(width, height)
    margin.rows = [
        [piece.rows[min(max(y - 1, 0), piece.height - 1)][min(max(x - 1, 0), piece.width - 1)] for x in range(width)]
        for y in range(height)
    ]
    return margin


def build_atlas(named_pieces):
    """Packs pieces into one texture, left to right in rows. Returns the texture and each piece's rectangle."""
    atlas = Texture(ATLAS_WIDTH, ATLAS_HEIGHT)
    rects = {}
    x = y = row_height = 0
    for name, piece in named_pieces.items():
        cell = extruded(piece)
        if x + cell.width > ATLAS_WIDTH:
            x, y, row_height = 0, y + row_height, 0
        if x + cell.width > ATLAS_WIDTH or y + cell.height > ATLAS_HEIGHT:
            raise BuildError(f'The pieces don\'t fit in a {ATLAS_WIDTH}x{ATLAS_HEIGHT} texture')
        atlas.paste(cell, x, y)
        rects[name] = (x + 1, y + 1, piece.width, piece.height)
        x += cell.width
        row_height = max(row_height, cell.height)
    return atlas, rects


def tga_bytes(texture):
    """An uncompressed 32-bit TGA with 8 alpha bits and the bottom-left origin, like the stock textures."""
    header = struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, texture.width, texture.height, 32, 8)
    body = bytearray()
    for row in reversed(texture.rows):
        for r, g, b, a in row:
            body += bytes((b, g, r, a))
    return header + bytes(body)


# SIDL XML: nodes are (tag, content, item). Content is None for an empty element, text, or a list of nodes.

def node(tag, content=None, item=None):
    return (tag, content, item)


def render(element, depth=1):
    tag, content, item = element
    pad = '  ' * depth
    opening = f'<{tag} item="{item}">' if item else f'<{tag}>'
    if content is None:
        return [f'{pad}<{tag} />']
    if not isinstance(content, list):
        text = str(content).lower() if isinstance(content, bool) else escape(str(content))
        return [f'{pad}{opening}{text}</{tag}>']
    lines = [f'{pad}{opening}']
    for child in content:
        lines += render(child, depth + 1)
    return lines + [f'{pad}</{tag}>']


def xml_document(elements):
    lines = [*XML_HEADER, f'  <!-- {LICENSE_NOTICE} -->']
    for element in elements:
        lines += render(element)
    lines.append('</XML>')
    return '\r\n'.join(lines) + '\r\n'


def point(tag, x, y):
    return node(tag, [node('X', x), node('Y', y)])


def size(width, height):
    return node('Size', [node('CX', width), node('CY', height)])


def color(tag, rgb):
    return node(tag, [node('R', rgb[0]), node('G', rgb[1]), node('B', rgb[2])])


def texture_info(name, width, height):
    return node('TextureInfo', [size(width, height)], name)


def animation(name, texture, rect):
    x, y, width, height = rect
    frame = [node('Texture', texture), point('Location', x, y), size(width, height), point('Hotspot', 0, 0),
             node('Duration', 1000)]
    return node('Ui2DAnimation', [node('Cycle', True), node('Frames', frame)], name)


def overlaps():
    return [node(f'Overlap{side}', 0) for side in ('Left', 'Top', 'Right', 'Bottom')]


def stock_buttons(tag, prefix):
    return node(tag, [node(state, f'{prefix}{state}') for state in BUTTON_STATES])


def stock_scrollbar(tag, up, down, thumb):
    return node(tag, [
        stock_buttons('UpButton', up),
        stock_buttons('DownButton', down),
        node('Thumb', [node(part, name) for part, name in thumb] + overlaps()),
        node('MiddleTextureInfo', 'scrollbar_gutter.tga'),
        node('MiddleTint', [node('Alpha', 255), node('R', 128), node('G', 128), node('B', 128)]),
    ])


def scrollbar():
    """The slim vertical scrollbar: chevron arrows, a thin rounded thumb, and a clear track."""
    def arrows(tag, way):
        return node(tag, [node(state, f'TUI_Scroll{way}{BUTTON_ART[state]}') for state in BUTTON_STATES])

    return node('VSBTemplate', [
        arrows('UpButton', 'Up'),
        arrows('DownButton', 'Down'),
        node('Thumb', [node('Top', 'TUI_ThumbTop'), node('Bottom', 'TUI_ThumbBottom'),
                       node('Middle', 'TUI_ThumbMiddle')] + overlaps()),
        node('MiddleTextureInfo', GUTTER_TEXTURE),
        node('MiddleTint', [node('Alpha', 255), node('R', 255), node('G', 255), node('B', 255)]),
    ])


def frame_template(name=FRAME_TEMPLATE, background=BACKGROUND_TEXTURE, edge=None, title=None, close=None,
                   title_left=None):
    """The overlay's panel as a window frame, with our slim scrollbar. The horizontal scrollbar and title
    boxes, which no TriageUI window shows, keep the base skin's look. edge, when given, is the animation
    for every side and corner of the border instead of the panel's rounded one. title, when given, is
    the animation for the title bar's left, middle and right (the chat windows' thin bar); otherwise the
    stock rounded title bar, which no other TriageUI window shows. title_left, when given, is the bar's left
    piece instead (the quantity window's name). close, when given, is the close box's animation for each of
    BUTTON_STATES (the item and quantity windows' Close button, the chat windows' X); otherwise the stock box."""
    border = {side: edge or f'TUI_Frame{piece}' for side, piece in BORDER_PIECES.items()}
    title_bar = {side: title or f'A_RoundedFrameTitle{side}' for side in ('Right', 'Left', 'Middle')}
    if title_left:
        title_bar['Left'] = title_left
    close_box = (node('CloseBox', [node(state, close[state]) for state in BUTTON_STATES]) if close
                 else stock_buttons('CloseBox', 'A_CloseBtn'))
    return node('WindowDrawTemplate', [
        node('Background', background),
        scrollbar(),
        stock_scrollbar('HSBTemplate', 'A_HSBLeft', 'A_HSBRight',
                        [('Right', 'A_HSBThumbRight'), ('Left', 'A_HSBThumbLeft'), ('Middle', 'A_HSBThumbMiddle')]),
        close_box,
        stock_buttons('MinimizeBox', 'A_MinimizeBtn'),
        stock_buttons('TileBox', 'A_TileBtn'),
        node('Border', [node(side, art) for side, art in border.items()] + overlaps()),
        node('Titlebar', [node(side, art) for side, art in title_bar.items()] + overlaps()),
    ], name)


def shared_definitions(rects):
    """What every TriageUI window uses: the textures, every piece's animation and the frame template."""
    item_close = {state: f'TUI_ItemClose{BUTTON_ART[state]}' for state in BUTTON_STATES}
    return [
        texture_info(PIECES_TEXTURE, ATLAS_WIDTH, ATLAS_HEIGHT),
        texture_info(BACKGROUND_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        texture_info(PERCENT_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        texture_info(FIELD_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        texture_info(GUTTER_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        texture_info(DIVIDER_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        *(animation(f'TUI_{name}', PIECES_TEXTURE, rect) for name, rect in rects.items()),
        # Far wider than its texture: the client repeats or stretches it, and only the first % is ever
        # inside the clip.
        animation('TUI_PercentSign', PERCENT_TEXTURE, (0, 0, SHOWN_REACH, PERCENT_GLYPH_HEIGHT)),
        # The stock slot backgrounds the client paints by name, redefined (see REPLACED_ANIMATIONS): clear
        # rows the slot's size, a harmful one with its red bars (see HELPFUL_RGBA and HARMFUL_RGBA).
        animation('BlueIconBackground', PIECES_TEXTURE, rects['HelpfulRow']),
        animation('RedIconBackground', PIECES_TEXTURE, rects['HarmfulRow']),
        # The spellbook slot's art, which the client names itself (default's is a dark 48px square; poweroftwo's, at its
        # slots' size, is its "blank spot"): clear at a spell's slot, like the slot's own.
        animation('A_SpellBookSlot', PIECES_TEXTURE, rects['BookSlot']),
        # The slider's left end cap, with no width (see SLIDER_TEMPLATE): the client draws one, so it must be there.
        animation('TUI_SliderCapLeft', PIECES_TEXTURE, (*rects['SliderCapRight'][:2], 0, SLIDER_HEIGHT)),
        frame_template(),
        # The chat windows' frame: the same, with the thin title bar to drag them by (see TITLE_HEIGHT) and its X (see
        # CHAT_CLOSE_SIZE).
        frame_template(CHAT_TEMPLATE, title='TUI_TitleBar',
                       close={state: f'TUI_ChatClose{BUTTON_ART[state]}' for state in BUTTON_STATES}),
        # The item and quantity windows': the same with a title bar tall enough for their Close button, the close box
        # (see ITEM_FILE).
        frame_template(ITEM_TEMPLATE, title='TUI_ItemTitleBar', close=item_close),
        # The quantity window's: the item window's with its name painted on the bar's left (see QUANTITY_TITLE_INK).
        frame_template(QUANTITY_TEMPLATE, title='TUI_ItemTitleBar', close=item_close, title_left='TUI_QuantityTitle'),
        # The chat input's field: a plain strip darker than the panel, outlined by a 1px line in the
        # window edge's color, a faint light line against both the field and the panel around it.
        frame_template(FIELD_TEMPLATE, FIELD_TEXTURE, edge='TUI_FieldEdge'),
        # The chat input box's: nothing drawn (see EDIT_TEMPLATE).
        frame_template(EDIT_TEMPLATE, GUTTER_TEXTURE, edge='TUI_Clear'),
        # A divider standing up: only its background, the row divider's color (see DIVIDER_TEMPLATE).
        frame_template(DIVIDER_TEMPLATE, DIVIDER_TEXTURE, edge='TUI_Clear'),
        # A dropdown's box and its open list: the panel, opaque, in a 1px outline like the chat input's (see
        # COMBO_TEMPLATE), and its arrow.
        frame_template(COMBO_TEMPLATE, edge='TUI_FieldEdge'),
        node('ButtonDrawTemplate', [node(state, f'TUI_ComboDown{BUTTON_ART[state]}') for state in BUTTON_STATES],
             COMBO_BUTTON),
        # The Actions window's tab and page borders: clear pieces that place the tabs and pages (see
        # TAB_BORDER), every one the stock templates have.
        node('FrameTemplate', [node(side, f'TUI_TabBorder{side}') for side in TAB_BORDER_PIECES] + overlaps(),
             TAB_BORDER),
        node('FrameTemplate', [node(side, f'TUI_PageBorder{side}') for side in PAGE_BORDER_PIECES] + overlaps(),
             PAGE_BORDER),
        node('FrameTemplate', [node(side, f'TUI_ListPageBorder{side}') for side in LIST_PAGE_BORDER_PIECES]
             + overlaps(), LIST_PAGE_BORDER),
        # A list column's heading strip (see LIST_HEADER).
        node('FrameTemplate', [node(side, 'TUI_ListHeaderWash') for side in ('Left', 'Middle', 'Right')] + overlaps(),
             LIST_HEADER),
        # The quantity window's slider: the knob in every state, the track and its end caps (see SLIDER_TEMPLATE).
        node('SliderDrawTemplate', [
            node('Thumb', [node(state, f'TUI_SliderKnob{BUTTON_ART[state]}') for state in BUTTON_STATES]),
            node('Background', 'TUI_SliderTrack'),
            node('EndCapRight', 'TUI_SliderCapRight'),
            node('EndCapLeft', 'TUI_SliderCapLeft'),
        ], SLIDER_TEMPLATE),
    ]


def with_definitions(base_animations, definitions, stranded=()):
    """The base skin's EQUI_Animations.xml text with our definitions added before its closing tag, and its
    own definitions of the animations we redefine (REPLACED_ANIMATIONS) taken out, so each is defined once.
    stranded are definitions (as text) from the base's copies of the files we replace, kept here so its
    other windows still find them."""
    for name in REPLACED_ANIMATIONS:
        base_animations = re.sub(rf'[ \t]*<Ui2DAnimation\s+item\s*=\s*"{name}"\s*>.*?</Ui2DAnimation>[ \t]*(\r?\n)?',
                                 '', base_animations, flags=re.S)
    end = base_animations.lower().rfind('</xml>')
    if end < 0:
        raise BuildError(f'The base skin\'s {ANIMATIONS_FILE} has no closing </XML>')
    newline = '\r\n' if '\r\n' in base_animations else '\n'
    head = base_animations[:end].rstrip(' \t')
    if head and not head.endswith(('\r', '\n')):
        head += newline
    lines = []
    if stranded:
        lines.append('  <!-- TriageUI: kept from the base skin\'s copies of the windows TriageUI replaces -->')
        for text in stranded:
            lines += ['  ' + text.strip().splitlines()[0]] + text.strip().splitlines()[1:]
    # After the base's and the stranded definitions, since it covers only ours.
    lines.append(f'  <!-- {LICENSE_NOTICE} -->')
    lines.append('  <!-- TriageUI: the shared frame, bar and button pieces -->')
    for element in definitions:
        lines += render(element)
    return head + newline.join(line.rstrip('\r') for line in lines) + newline + base_animations[end:]


# Window parts

def label(name, eq_type, rect, text, align_right=False, screen_id=None, rgb=TEXT_RGB, font=TEXT_FONT,
          align_center=False):
    x, y, width, height = rect
    children = [node('ScreenID', screen_id)] if screen_id else []
    if eq_type is not None:
        children.append(node('EQType', eq_type))
    children += [
        node('Font', font),
        node('RelativePosition', True),
        point('Location', x, y),
        size(width, height),
        node('Text', text),
        color('TextColor', rgb),
        node('NoWrap', True),
        node('AlignCenter', align_center),
        node('AlignRight', align_right),
        node('AlignLeft', not (align_right or align_center)),
        node('Style_Transparent', True),
        node('Style_Tooltip', False),
    ]
    return node('Label', children, name)


def static_text(name, screen_id, rect, align_right=False, align_center=False, rgb=TEXT_RGB):
    """Text the client writes into a StaticText it looks up (the spellbook's names and page numbers), in font 3 and
    rgb, on one line. Not a label(): SIDL.xml makes StaticText a static piece, which never takes a click, and gives it
    no EQType, AlignLeft or Style_ flags, so it has only what the schema lists."""
    x, y, width, height = rect
    return node('StaticText', [
        node('ScreenID', screen_id),
        node('Font', TEXT_FONT),
        node('RelativePosition', True),
        point('Location', x, y),
        size(width, height),
        node('Text', ''),
        color('TextColor', rgb),
        node('NoWrap', True),
        node('AlignCenter', align_center),
        node('AlignRight', align_right),
    ], name)


def tooltip_spot(name, rect, tooltip):
    """An empty label over rect that only shows tooltip when pointed at, as stock labels can. Like duxaUI's
    effect names, which sit over the slot buttons and let their clicks through, it has no Style_Transparent."""
    x, y, width, height = rect
    return node('Label', [
        node('RelativePosition', True),
        point('Location', x, y),
        size(width, height),
        node('Text', ''),
        node('TooltipReference', tooltip),
        node('NoWrap', True),
    ], name)


def health_readout(item, number_type, gauge_type, top, right, number_id, rgb=TEXT_RGB):
    """Health at the right end of a line (see percent_readout()), the % hiding along with whoever the line is
    about."""
    return percent_readout(f'{item}_HPLabel', f'{item}_HPPercent', number_type, gauge_type, top, right, number_id,
                           rgb)


def percent_readout(number_name, percent_name, number_type, gauge_type, top, right, number_id=None, rgb=TEXT_RGB):
    """A percentage at the right end of a line: the number (label number_type, right-aligned) with a drawn %
    after it, ending at right, both in rgb. The % shows only while gauge_type is above 0.

    Returns the %'s gauge, defined but not a piece of the window, and the pieces.
    """
    percent_x = right - PERCENT_WIDTH
    percent, percent_clip = shown_with_target(
        percent_name, 'TUI_PercentSign',
        (percent_x, top + PERCENT_INK_TOP, PERCENT_WIDTH, PERCENT_GLYPH_HEIGHT), eq_type=gauge_type, tint=rgb)
    # Blank until the client fills it: a 0 showed in the group window's empty slots.
    number = label(number_name, number_type, (percent_x - NUMBER_WIDTH, top, NUMBER_WIDTH, TEXT_HEIGHT), '',
                   align_right=True, screen_id=number_id, rgb=rgb)
    return percent, [number, percent_clip]


def gauge(name, screen_id, eq_type, rect, fill, tint, track=None, text_rgb=TEXT_RGB, text_at=None, bar_at=(0, 0),
          text=None, font=TEXT_FONT):
    """A bar. Its own text (a name, for most EQTypes) shows at text_at inside it, or is hidden when None.

    bar_at is where the bar starts inside the gauge. The fill and track must be as big as the rest of the gauge.
    screen_id is None for gauges the client doesn't need to find.
    """
    x, y, width, height = rect
    children = [node('ScreenID', screen_id)] if screen_id else []
    children += [
        node('EQType', eq_type),
        node('Font', font),
        color('TextColor', text_rgb),
        node('RelativePosition', True),
        point('Location', x, y),
        size(width, height),
    ]
    if text_at is None:
        children += [node('Text'), node('TextOffsetY', 8000)]
    else:
        if text:
            children.append(node('Text', text))  # what shows until the client sets it
        children += [node('TextOffsetX', text_at[0]), node('TextOffsetY', text_at[1])]
    children += [
        node('GaugeOffsetX', bar_at[0]),
        node('GaugeOffsetY', bar_at[1]),
        node('Style_Transparent', False),
        color('FillTint', tint),
        node('DrawLinesFill', False),
        node('GaugeDrawTemplate', ([node('Background', track)] if track else []) + [node('Fill', fill)]),
    ]
    return node('Gauge', children, name)


def clip(name, rect, parts):
    """A transparent child window that shows only what of parts falls inside rect, as duxaUI does."""
    x, y, width, height = rect
    return node('Screen', [
        node('RelativePosition', True),
        point('Location', x, y),
        size(width, height),
        node('Style_Transparent', True),
    ] + [node('Pieces', part[2]) for part in parts], name)


def shown_with_target(name, art, rect, eq_type=6, tint=TEXT_RGB):
    """art in rect, tinted, shown only while eq_type's gauge is above 0 (see SHOWN_REACH): by default the
    target's health, so only while something is targeted.

    Returns the gauge, which belongs in the window file but isn't one of the window's pieces, and the
    clip, which is.
    """
    x, y, width, height = rect
    hidden = gauge(name, None, eq_type, (0, 0, SHOWN_REACH, height), art, tint)
    return hidden, clip(f'{name}_Clip', rect, [hidden])


def twin_bar(name, screen_id, eq_type):
    """The target's thin health bar on its second line, with its track."""
    return gauge(name, screen_id, eq_type, (LEFT, TWIN_BAR_TOP, TWIN_BAR_WIDTH, TWIN_BAR_HEIGHT),
                 'TUI_TwinFill', TEXT_RGB, track='TUI_TwinTrack')


def button_art(width, height, label, state, style=BUTTON_STYLE):
    """The name of a button's art for one style, size, label and state (art is drawn at its own size, with
    its label in it)."""
    return f'Button{style}{width}x{height}{label}{state}'


def button(name, screen_id, label, x, y, width=BUTTON_WIDTH, height=BUTTON_HEIGHT, tooltip=None, font=None,
           text=''):
    """A button whose label is drawn in its art (see LABEL_GLYPHS), so its own text is empty. With font, the
    button shows text in that font over art with no label, or, with text empty, what the game writes there
    (an ability's or a social's name)."""
    children = [node('ScreenID', screen_id)] if screen_id else []
    if font is not None:
        children.append(node('Font', font))
    children += [
        node('RelativePosition', True),
        point('Location', x, y),
        size(width, height),
        node('Style_Transparent', False),
    ]
    if tooltip:
        children.append(node('TooltipReference', tooltip))
    children += [node('Style_Checkbox', False), node('Text', text)]
    if font is not None:
        children.append(color('TextColor', TEXT_RGB))
    return node('Button', children + [button_template(width, height, label)], name)


def button_template(width, height, label):
    """A button's art in every state, drawn at its size with its label in it."""
    return node('ButtonDrawTemplate', [node(state, f'TUI_{button_art(width, height, label, BUTTON_ART[state])}')
                                       for state in BUTTON_STATES])


def anchored_button(name, screen_id, label, left, bottom, width, height, layout_height):
    """A button like button()'s, width x height, pinned left in from the window's inner left edge and bottom up
    from its bottom (the window's width never changes, so its right is measured from the left too). Its Location
    and Size are only what the client's own layout reads: the Size's height is layout_height (see
    CONTAINER_FILE)."""
    return node('Button', [
        node('ScreenID', screen_id),
        node('RelativePosition', True),
        point('Location', 0, 0),
        size(width, layout_height),
        *anchor_nodes((left, bottom + height, left + width, bottom), True, right_from_left=True),
        node('Style_Transparent', False),
        node('Style_Checkbox', False),
        node('Text', ''),
        button_template(width, height, label),
    ], name)


def icon_square(name, screen_id, x, y, tooltip, icon, side, checkbox, art, height=None, prefix='Toggle'):
    """A square button, side wide (or height tall, when wider than it is tall), showing an icon in every state,
    its name in its tooltip (none when tooltip is None). Its art is TUI_<prefix><icon><state>."""
    return node('Button', [
        node('ScreenID', screen_id),
        node('RelativePosition', True),
        point('Location', x, y),
        size(side, height or side),
        node('Style_Transparent', False),
        *([node('TooltipReference', tooltip)] if tooltip else []),
        node('Style_Checkbox', checkbox),
        node('ButtonDrawTemplate', [node(state, f'TUI_{prefix}{icon}{art[state]}') for state in BUTTON_STATES]),
    ], name)


def toggle_button(name, screen_id, x, y, tooltip, icon, width=TOGGLE_SIZE):
    """A square button (or one TOGGLE_SIZE tall and width wide) that stays pressed while what it opens is open,
    showing an icon in every state."""
    return icon_square(name, screen_id, x, y, tooltip, icon, width, True, TOGGLE_ART, TOGGLE_SIZE)


def icon_button(name, screen_id, x, y, tooltip, icon, side=TOGGLE_SIZE):
    """A command's square button (the social page arrows), lit like an open toggle while pressed and dimmed
    while the client disables it."""
    return icon_square(name, screen_id, x, y, tooltip, icon, side, False, ICON_ART)


def filter_toggle(name, screen_id, x, y, tooltip, color_name):
    """A tracking filter: a FILTER_SIZE checkbox showing its con color's square, bright while pressed (see
    FILTER_SWATCH)."""
    return icon_square(name, screen_id, x, y, tooltip, color_name, FILTER_SIZE, True, TOGGLE_ART, prefix='Filter')


def combobox(name, screen_id, rect, choices):
    """A dropdown the client fills with its choices, drawn by COMBO_TEMPLATE with COMBO_BUTTON's arrow, in the windows'
    font. Its open list is tall enough for choices rows (see COMBO_ROW_HEIGHT)."""
    x, y, width, height = rect
    return node('Combobox', [
        node('ScreenID', screen_id),
        node('Font', TEXT_FONT),
        node('RelativePosition', True),
        point('Location', x, y),
        size(width, height),
        color('TextColor', TEXT_RGB),
        node('Style_Border', True),
        node('DrawTemplate', COMBO_TEMPLATE),
        node('Button', COMBO_BUTTON),
        node('ListHeight', choices * COMBO_ROW_HEIGHT + 2),
    ], name)


def hidden_button(name, screen_id, x=0, y=0):
    """A button the client looks up when it builds a window (it reports an error if one is missing) but
    the user doesn't want: no size, no text and clear art, so it can't be seen or clicked. It sits at x, y,
    which matters only where the client measures it (see BAG_ICON_SPOT)."""
    return node('Button', [
        node('ScreenID', screen_id),
        node('RelativePosition', True),
        point('Location', x, y),
        size(0, 0),
        node('Style_Transparent', True),
        node('Style_Checkbox', False),
        node('Text', ''),
        node('ButtonDrawTemplate', [node(state, 'TUI_Clear') for state in BUTTON_STATES]),
    ], name)


def window(item, title, height, parts, tooltip=None, width=WINDOW_WIDTH, inner=(), sizable=False,
           template=FRAME_TEMPLATE, title_bar=False, font=None, close_box=False):
    """A window without a title bar, like the overlays with their header hidden, holding parts in drawing order.

    title None leaves the window's name to the client, as for chat windows. inner are defined first but
    aren't pieces of the window: they belong to clips or tab pages among the parts. title_bar draws template's title
    bar (the chat windows' thin one); font is the window's own, for the name the client writes on it. close_box
    puts template's close box on the bar (the item and quantity windows' Close button, the chat windows' X).
    """
    children = [node('ScreenID')]
    if font is not None:
        children.append(node('Font', font))
    children += [
        node('RelativePosition', False),
        point('Location', 200, 200),
        size(width, height),
    ]
    if title is not None:
        children.append(node('Text', title))
    children += [
        node('Style_VScroll', False),
        node('Style_HScroll', False),
        node('Style_Transparent', False),
    ]
    if tooltip:
        children.append(node('TooltipReference', tooltip))
    children += [
        node('DrawTemplate', template),
        node('Style_Titlebar', title_bar),
        node('Style_Closebox', close_box),
        node('Style_Minimizebox', False),
        node('Style_Border', True),
        node('Style_Sizable', sizable),
    ]
    return list(inner) + parts + [node('Screen', children + [node('Pieces', part[2]) for part in parts], item)]


def anchor_nodes(offsets, top_from_bottom, right_from_left=False, bottom_from_top=False):
    """AutoStretch and the anchors that pin a control to its window's inner edges: offsets are (left, top, right,
    bottom) in from them, the bottom measured up from the bottom edge. top_from_bottom measures the top up from the
    bottom too, right_from_left the right from the left edge and bottom_from_top the bottom down from the top."""
    left, top, right, bottom = offsets
    return [
        node('AutoStretch', True),
        node('LeftAnchorOffset', left),
        node('TopAnchorOffset', top),
        node('RightAnchorOffset', right),
        node('BottomAnchorOffset', bottom),
        node('TopAnchorToTop', not top_from_bottom),
        node('RightAnchorToLeft', right_from_left),
        node('BottomAnchorToTop', bottom_from_top),
    ]


def stretched(tag, name, screen_id, template, offsets, top_from_bottom, extra):
    """A control that stretches with a resizable window. offsets are (left, top, right, bottom) in from
    the window's inner edges; top_from_bottom measures the top edge up from the bottom instead."""
    return node(tag, [
        node('ScreenID', screen_id),
        node('DrawTemplate', template),
        node('RelativePosition', True),
        *anchor_nodes(offsets, top_from_bottom),
    ] + extra, name)


# The windows

def target_window():
    """The target's name across the first line, and a thin HP bar, then the HP %, on the second."""
    # Zeal blanks the number without a target, and the drawn % hides with it. The name, bar and health %
    # are in the text's color (the user tried a soft red, '#e88080', and went back).
    percent, readout = health_readout('TUI_Target', 29, 6, TARGET_LINE2, TARGET_RIGHT, 'HPLabel')
    return window('TargetWindow', 'Target', TARGET_HEIGHT, [
        label('TUI_Target_Name', 28, (LEFT, 0, TARGET_RIGHT - LEFT, TEXT_HEIGHT), 'TargetName'),
        twin_bar('TUI_Target_HP', 'TargetHP', 6),
        *readout,
    ], tooltip='Your Current Target', width=TARGET_WIDTH, inner=[percent])


def pet_window():
    """Your pet in the target window's shape: its name on the first line, its health bar and HP % on the
    second, and its commands below in three columns of related pairs."""
    # The drawn % shows only while you have a pet (gauge 16 above 0).
    percent, readout = health_readout('TUI_PIW', 69, 16, TARGET_LINE2, PET_RIGHT, 'PIW_PetHPLabel')
    # One gauge for the name and the bar, as in the default skin: its own text is the pet's name ("No Pet"
    # without one) and its bar starts where the target's does, two pixels shorter, like the window.
    health = gauge('TUI_PIW_PetHPGauge', 'PetHPGauge', 16, (LEFT, 0, PIW_BAR_WIDTH, TWIN_BAR_TOP + TWIN_BAR_HEIGHT),
                   'TUI_PIWFill', TEXT_RGB, track='TUI_PIWTrack', text_at=(0, 0), bar_at=(0, TWIN_BAR_TOP),
                   text='No Pet')
    commands = []
    for c, column in enumerate(PET_COLUMNS):
        x = LEFT + c * (PET_BUTTON_WIDTH + BUTTON_GAP)
        for r, (screen_id, text, tooltip) in enumerate(column):
            commands.append(button(f'TUI_PIW_{screen_id}', screen_id, text, x,
                                   PET_BUTTONS_TOP + r * (BUTTON_HEIGHT + PET_PAIR_GAP),
                                   width=PET_BUTTON_WIDTH, tooltip=tooltip))
    commands += [hidden_button(f'TUI_PIW_{screen_id}', screen_id) for screen_id in PET_HIDDEN]
    rows = max(len(column) for column in PET_COLUMNS)
    height = 2 * BORDER + PET_BUTTONS_TOP + rows * BUTTON_HEIGHT + (rows - 1) * PET_PAIR_GAP + BOTTOM_GAP
    return window('PetInfoWindow', 'Pet Info', height, [
        health,
        *readout,
        *commands,
    ], width=PET_WIDTH, inner=[percent])


def group_window():
    """Each member as a line, name and health %, with a thin bar under the name, and their pet on its own
    indented line below.

    Clicking a gauge targets whoever it shows, so each member and pet is one full-row gauge showing the
    name as its own text: pets are as easy to click as players, instead of a 2px bar.
    """
    dividers, gauges, labels, inner = [], [], [], []
    for n in range(1, GROUP_SIZE + 1):
        top = (n - 1) * MEMBER_PITCH
        if n > 1:
            dividers.append(picture(f'TUI_GW_Divider{n}', 'TUI_GroupDivider',
                                    (LEFT, top - DIVIDER_TO_NAME - DIVIDER_HEIGHT, GROUP_CONTENT_WIDTH, DIVIDER_HEIGHT)))
        # The name (the gauge's own text) and the bar under it, both in GROUP_RGB. No track, so an empty slot
        # shows no bar.
        gauges.append(gauge(f'TUI_GW_Gauge{n}', f'Gauge{n}', 10 + n, (LEFT, top, GROUP_CONTENT_WIDTH, MEMBER_LINE_HEIGHT),
                            'TUI_MemberGaugeFill', GROUP_RGB, text_rgb=GROUP_RGB, text_at=(0, 0),
                            bar_at=(0, MEMBER_BAR_TOP)))
        gauges.append(gauge(f'TUI_GW_PetGauge{n}', f'PetGauge{n}', 16 + n, (LEFT, top + PET_TOP, GROUP_CONTENT_WIDTH, PET_HEIGHT),
                            'TUI_PetGaugeFill', PET_RGB, text_rgb=PET_RGB, text_at=(PET_INDENT, 0),
                            bar_at=(PET_INDENT, PET_TEXT_HEIGHT + PET_BAR_GAP), font=PET_FONT))
        # "72%" ending at the row's padding; the % shows only while the slot has a member. The client
        # writes a 0 into an empty slot's number, which a skin can't hide: art drawn over it shows only where a
        # gauge has a value, and an empty slot's gauge has none.
        percent, readout = health_readout(f'TUI_GW{n}', 34 + n, 10 + n, top, GROUP_RIGHT, f'HPLabel{n}', GROUP_RGB)
        inner.append(percent)
        labels += readout
    buttons_top = (GROUP_SIZE - 1) * MEMBER_PITCH + MEMBER_HEIGHT + BUTTON_ROW_GAP
    buttons = [button(f'TUI_GW_{screen_id}', screen_id, label, LEFT + column * (BUTTON_WIDTH + BUTTON_GAP), buttons_top,
                      width=GROUP_BUTTON_WIDTHS[column])
               for screen_id, label, column in GROUP_BUTTONS]
    height = 2 * BORDER + buttons_top + BUTTON_HEIGHT + BOTTOM_GAP
    return window('GroupWindow', 'Group', height, dividers + gauges + labels + buttons, inner=inner,
                  width=GROUP_WIDTH)


def casting_window():
    """'Casting:' and the spell you're casting (Zeal's label 134), above a bar that fills as the cast
    completes. The target window's size, the bar at the height of its health bar but across the whole
    width between the paddings (the user's request)."""
    spell_x = LEFT + CASTING_PREFIX_WIDTH
    # All in the soft red, the bar softened like every bar (the user's requests). Zeal leaves label 134's color
    # to the skin, so ours holds in game.
    return window('CastingWindow', 'Casting Time', TARGET_HEIGHT, [
        label('TUI_Casting_Prefix', None, (LEFT, 0, CASTING_PREFIX_WIDTH, TEXT_HEIGHT), 'Casting:', rgb=SPELL_RGB),
        label('TUI_Casting_Spell', 134, (spell_x, 0, TARGET_RIGHT - spell_x, TEXT_HEIGHT), '',
              screen_id='Casting_Spell', rgb=SPELL_RGB),
        gauge('TUI_Casting_Gauge', 'Gauge', 7, (LEFT, TWIN_BAR_TOP, CAST_BAR_WIDTH, TWIN_BAR_HEIGHT), 'TUI_CastFill',
              SPELL_RGB, track='TUI_CastTrack'),
    ], width=TARGET_WIDTH)


def breath_window():
    """'Air Remaining' above a bar that empties as your air runs out (gauge 8): the casting window's twin, so the
    two line up when stacked, in soft cyan (the user's picks). No label gives the air as a number."""
    return window('BreathWindow', 'Air Remaining', TARGET_HEIGHT, [
        label('TUI_Breath_Caption', None, (LEFT, 0, TARGET_RIGHT - LEFT, TEXT_HEIGHT), 'Air Remaining', rgb=AIR_RGB),
        # The casting bar's art, which is this bar's size.
        gauge('TUI_Breath_Gauge', 'Gauge', 8, (LEFT, TWIN_BAR_TOP, CAST_BAR_WIDTH, TWIN_BAR_HEIGHT), 'TUI_CastFill',
              AIR_RGB, track='TUI_CastTrack'),
    ], tooltip='The Breath Meter', width=TARGET_WIDTH)


def chat_window():
    """Every chat window: a really thin title bar to drag it by, the chat straight on the panel with a
    slim scrollbar, and the input line on a plain strip along the bottom. All of it follows the window
    as it's resized."""
    output = stretched('STMLbox', 'TUI_CW_ChatOutput', 'CWChatOutput', FRAME_TEMPLATE,
                       (LEFT, LEFT, LEFT, LEFT + INPUT_HEIGHT + INPUT_GAP), False,
                       # Transparent: the text sits on the window's own panel, with no second one behind it.
                       [node('Style_VScroll', True), node('Style_Border', False), node('Style_Transparent', True)])
    # The field's strip across the whole width: a child window drawing its background and a 1px outline
    # (the user wanted a border with slight contrast to the colors on either side of it).
    strip_left, strip_right = LEFT, LEFT
    strip = node('Screen', [
        node('RelativePosition', True),
        node('AutoStretch', True),
        node('LeftAnchorOffset', strip_left),
        node('TopAnchorOffset', LEFT + INPUT_HEIGHT),
        node('RightAnchorOffset', strip_right),
        node('BottomAnchorOffset', LEFT),
        node('TopAnchorToTop', False),
        node('RightAnchorToLeft', False),
        node('BottomAnchorToTop', False),
        node('DrawTemplate', FIELD_TEMPLATE),
        node('Style_Transparent', False),
        node('Style_Border', True),
    ], 'TUI_CW_InputStrip')
    # The input box on the strip, inset FIELD_PADDING each side, drawing nothing itself so the strip shows.
    field = stretched('Editbox', 'TUI_CW_ChatInput', 'CWChatInput', EDIT_TEMPLATE,
                      (strip_left + FIELD_PADDING, LEFT + INPUT_HEIGHT, strip_right + FIELD_PADDING, LEFT), True,
                      [node('Style_Border', False), node('Style_Transparent', True)])
    width, height = CHAT_SIZE
    # The thin title bar (see TITLE_HEIGHT) with the client's name for the window in a small font, and its X.
    return window('ChatWindow', None, height, [output, strip, field], width=width, sizable=True,
                  template=CHAT_TEMPLATE, title_bar=True, font=TITLE_FONT, close_box=True)


def selector_window():
    """The buttons that open and close the other windows: one row of icon toggles."""
    toggles = [toggle_button(f'TUI_{screen_id}', screen_id, LEFT + i * (TOGGLE_SIZE + BUTTON_GAP), LEFT, tooltip, icon)
               for i, (screen_id, tooltip, icon) in enumerate(SELECTOR_BUTTONS)]
    toggles += [hidden_button(f'TUI_{screen_id}', screen_id) for screen_id in SELECTOR_HIDDEN]
    return window('SelectorWindow', 'Window Selector', SELECTOR_HEIGHT, toggles, width=SELECTOR_WIDTH)


def page(item, screen_id, tooltip, icon, parts):
    """One of a tab box's pages, holding parts: see-through, so the window's panel shows, and its tab the
    icon's toggle (or the tab with its name, for the AA window's), lit (the open look) while the page is shown (see
    tab_art()). tooltip None gives it none."""
    return node('Page', [
        node('ScreenID', screen_id),
        node('RelativePosition', True),
        node('Style_VScroll', False),
        node('Style_HScroll', False),
        node('Style_Transparent', True),
        *([node('TooltipReference', tooltip)] if tooltip else []),
        node('DrawTemplate', FRAME_TEMPLATE),
        node('Style_Border', False),
        node('TabIcon', f'TUI_Tab{icon}Normal'),
        node('TabIconActive', f'TUI_Tab{icon}Pressed'),
    ] + [node('Pieces', part[2]) for part in parts], item)


def actions_window():
    """The stock four pages behind icon tabs, the actions in two columns of buttons: Camp, Sit or Stand, Run or
    Walk and Invite or Follow; the abilities; the attacks and combat abilities; and the socials under their
    page arrows. A divider runs under the tabs. Positions on a page are from its top left, a padding under the
    divider and in from the window's sides (the tab box places the pages there: see TAB_BORDER)."""
    def cell(column, row, top=0):
        # A button's spot: (x, y, width).
        return sum(ACTION_WIDTHS[:column]) + column * BUTTON_GAP, top + row * ACTION_ROW_STEP, ACTION_WIDTHS[column]

    def grid(spots):
        # The spots left to right then down; the pairs the client swaps share a spot. The game writes the name
        # where the text is None.
        buttons = []
        for n, spot in enumerate(spots):
            x, y, width = cell(n % ACTION_COLUMNS, n // ACTION_COLUMNS)
            buttons += [button(f'TUI_AW_{screen_id}', screen_id, '', x, y, width, TEXT_BUTTON_HEIGHT,
                               font=ACTION_FONT, text=text or '') for screen_id, text in spot]
        return buttons

    main = grid(MAIN_SPOTS) + [hidden_button(f'TUI_AW_{screen_id}', screen_id) for screen_id in MAIN_HIDDEN]
    arrows = [icon_button(f'TUI_AW_{screen_id}', screen_id, x, 0, tooltip, icon, ARROW_SIZE)
              for x, (screen_id, tooltip, icon) in zip((0, ACTIONS_CONTENT_WIDTH - ARROW_SIZE), SOCIAL_ARROWS)]
    number_x = ARROW_SIZE + BUTTON_GAP
    number = label(f'TUI_AW_{SOCIAL_PAGE_LABEL}', None,
                   (number_x, SOCIAL_PAGE_LABEL_TOP, ACTIONS_CONTENT_WIDTH - 2 * number_x, TEXT_HEIGHT), '1',
                   screen_id=SOCIAL_PAGE_LABEL, align_center=True)
    socials = [arrows[0], number, arrows[1]]
    for n, screen_id in enumerate(SOCIALS):
        column, row = divmod(n, SOCIAL_SLOT_ROWS)  # down each column first
        if row >= SOCIAL_ROWS:  # the hidden bottom rows
            socials.append(hidden_button(f'TUI_AW_{screen_id}', screen_id))
            continue
        x, y, width = cell(column, row, SOCIALS_TOP)
        socials.append(button(f'TUI_AW_{screen_id}', screen_id, '', x, y, width, TEXT_BUTTON_HEIGHT, font=ACTION_FONT))
    abilities = grid(ABILITY_SPOTS)
    combat = grid(COMBAT_SPOTS)
    # Each page's parts, then the page, all defined before the tab box that shows them.
    inner = []
    for (item, screen_id, tooltip, icon), parts in zip(ACTIONS_PAGES, (main, abilities, combat, socials)):
        inner += parts + [page(item, screen_id, tooltip, icon, parts)]
    tabs = node('TabBox', [
        node('ScreenID', 'ACTW_ActionsSubwindows'),
        node('Font', TEXT_FONT),  # its height + 8 is the least tab row, which our tabs are taller than
        node('RelativePosition', True),
        point('Location', 0, 0),
        size(TAB_BOX_WIDTH, ACTIONS_INSIDE_HEIGHT),  # TAB_OVERHANG past the inside on the right
        node('TabBorderTemplate', TAB_BORDER),
        node('PageBorderTemplate', PAGE_BORDER),
    ] + [node('Pages', item) for item, *_ in ACTIONS_PAGES], 'TUI_AW_Tabs')
    # Over each tab, its page's name as a tooltip (see TAB_LEFTS).
    names = [tooltip_spot(f'TUI_AW_{icon}Tab', (x, TOGGLES_TOP, width, TOGGLE_SIZE), page_name)
             for (_, _, page_name, icon), x, width in zip(ACTIONS_PAGES, TAB_LEFTS, TAB_WIDTHS)]
    # The divider under the tabs: the Effects window's, at the content row's width.
    divider = picture('TUI_AW_TabDivider', 'TUI_ActionsDivider',
                      (LEFT, TAB_DIVIDER_TOP, ACTIONS_CONTENT_WIDTH, DIVIDER_HEIGHT))
    return window('ActionsWindow', 'Actions', ACTIONS_HEIGHT, [tabs, *names, divider], width=ACTIONS_WIDTH,
                  inner=inner)


def picture(name, animation_name, rect, screen_id=None):
    """A still picture: not a control, so it never takes a click. screen_id names one the client looks up (the
    compass's)."""
    x, y, width, height = rect
    return node('StaticAnimation', ([node('ScreenID', screen_id)] if screen_id else []) + [
        node('RelativePosition', True),
        point('Location', x, y),
        size(width, height),
        node('Animation', animation_name),
    ], name)


def effects_table(item, title, slots, first_name_type, prefix):
    """A table of effect slots, one row each: the client's slot button (ScreenID BuffN) across the row,
    inset (see SLOT_WIDTH), Zeal's time left at its start, then the spell's icon, with a red bar each side of
    a harmful one, and the spell's name (label first_name_type + N), rows ROW_PITCH apart with a divider
    between, in a window
    EFFECTS_WIDTH wide. The client looks up CLIENT_SLOTS buttons whatever the window shows, so the slots
    beyond are hidden."""
    dividers, buttons, names = [], [], []
    for n in range(slots):
        top = n * ROW_PITCH
        if n:
            dividers.append(picture(f'{prefix}_Divider{n}', 'TUI_RowDivider', (LEFT, top - 1, SLOT_WIDTH, 1)))
        buttons.append(node('Button', [
            node('ScreenID', f'Buff{n}'),
            node('RelativePosition', True),
            # The client places the slots itself, one per row here since two don't fit across; the Location
            # is where it puts them (see SLOT_X).
            point('Location', SLOT_X, top),
            size(SLOT_WIDTH, ROW_HEIGHT),
            node('Style_Transparent', False),
            node('Style_Checkbox', False),
            # The client paints Blue- or RedIconBackground and the spell's icon at runtime.
            node('ButtonDrawTemplate', [node('Normal', REPLACED_ANIMATIONS[0]), node('NormalDecal', BUFF_ICONS)]),
            point('DecalOffset', ROW_ICON_X - SLOT_X, ROW_ICON_MARGIN),  # within the slot
            node('DecalSize', [node('CX', ROW_ICON), node('CY', ROW_ICON)]),
        ], f'{prefix}_Buff{n}_Button'))
        names.append(label(f'{prefix}_Buff{n}_Name', first_name_type + n,
                           (ROW_NAME_X, top + (ROW_HEIGHT - TEXT_HEIGHT) // 2, EFFECTS_RIGHT - ROW_NAME_X,
                            TEXT_HEIGHT),
                           '', screen_id=f'Buff{n}Label'))
    hidden = [hidden_button(f'{prefix}_Buff{n}_Button', f'Buff{n}') for n in range(slots, CLIENT_SLOTS)]
    height = 2 * BORDER + slots * ROW_PITCH - 1
    # The names go over the buttons, as in duxaUI (whose names overlap its slots too). Both orders were
    # tried in game while the slots weren't hit-tested at all (see SLOT_WIDTH); neither was the cause.
    return window(item, title, height, dividers + buttons + names + hidden, width=EFFECTS_WIDTH)


def hidden_gauge(name, screen_id, eq_type):
    """A gauge the client looks up but the user doesn't want: no size and clear art."""
    return node('Gauge', [
        node('ScreenID', screen_id),
        node('EQType', eq_type),
        node('RelativePosition', True),
        point('Location', 0, 0),
        size(0, 0),
        node('Text'),
        node('TextOffsetY', 8000),
        node('GaugeDrawTemplate', [node('Fill', 'TUI_Clear')]),
    ], name)


def hidden_label(name, screen_id, x=0, y=0):
    """A label the client looks up (and may write in) but the user doesn't want: no size and no text, in the
    panel's color in case the client draws its text anyway. It sits at x, y, which matters only where the client
    measures it (see BAG_LABEL_SPOT)."""
    return label(name, None, (x, y, 0, 0), '', screen_id=screen_id, rgb=PANEL_RGBA[:3])


def listbox(name, screen_id, rect, tooltip, columns):
    """A list the client fills, on the window's own panel: only our slim scrollbar is drawn (see EDIT_TEMPLATE).
    columns are (heading, width), in the client's order; each column with a heading has the header strip (see
    LIST_HEADER), one with no width is hidden, and a list whose columns have no headings has no heading row (the
    tracking list, like the stock one). tooltip None gives the list none."""
    x, y, width, height = rect
    return node('Listbox', [
        node('ScreenID', screen_id),
        node('Font', TEXT_FONT),
        node('RelativePosition', True),
        point('Location', x, y),
        size(width, height),
        color('TextColor', TEXT_RGB),
        node('Style_VScroll', True),
        node('Style_Border', False),
        *([node('TooltipReference', tooltip)] if tooltip else []),
        node('DrawTemplate', EDIT_TEMPLATE),
    ] + [node('Columns', ([node('Header', LIST_HEADER)] if heading else [])
              + [node('Width', column_width), node('Heading', heading)])
         for heading, column_width in columns], name)


def player_window():
    """Health and Mana, each a line with its %, its "current/max" and a bar under it, Zeal's server tick under the
    mana bar, a line with your XP and AA rates, and the resists under them as a small table."""
    parts = []
    max_x = PLAYER_RIGHT - PLAYER_NUMBER_WIDTH
    slash_x = max_x - PLAYER_SLASH_WIDTH
    current_x = slash_x - PLAYER_NUMBER_WIDTH
    # The % two paddings and a digit before the current number, closer to the caption (at a padding they ran
    # together, then the user asked for one more character), in the values' green, shown by your own health, so
    # always.
    percent_right = current_x - 2 * PADDING - DIGIT_WIDTH
    percent_number_x = percent_right - PERCENT_WIDTH - NUMBER_WIDTH
    percents = []
    # (gauge ScreenID, gauge EQType, caption, % label EQType, current and max label EQTypes, bar tint, bar fill):
    # Zeal gives mana's current and max. The mana bar is solid, exactly the group window's names' blue (the
    # user's request).
    for n, (screen_id, eq_type, caption, percent_type, current_type, max_type, tint, fill) in enumerate((
            ('PlayerHP', 1, 'Health', 19, 17, 18, HP_RGB, 'TUI_PlayerFill'),
            ('PlayerMana', 2, 'Mana', 20, 124, 125, MANA_RGB, 'TUI_PlayerSolidFill'))):
        top = PLAYER_SECTIONS_TOP + n * PLAYER_SECTION_PITCH
        percent, readout = percent_readout(f'TUI_PW_{screen_id}Percent', f'TUI_PW_{screen_id}PercentSign',
                                           percent_type, 1, top, percent_right, rgb=VALUE_RGB)
        percents.append(percent)
        parts += [
            label(f'TUI_PW_{screen_id}Caption', None, (LEFT, top, percent_number_x - LEFT, TEXT_HEIGHT), caption,
                  rgb=CAPTION_RGB),
            *readout,
            label(f'TUI_PW_{screen_id}Current', current_type, (current_x, top, PLAYER_NUMBER_WIDTH, TEXT_HEIGHT), '',
                  align_right=True, rgb=VALUE_RGB),
            label(f'TUI_PW_{screen_id}Slash', None, (slash_x, top, PLAYER_SLASH_WIDTH, TEXT_HEIGHT), '/',
                  align_center=True, rgb=TEXT_RGB),
            label(f'TUI_PW_{screen_id}Max', max_type, (max_x, top, PLAYER_NUMBER_WIDTH, TEXT_HEIGHT), '', rgb=VALUE_RGB),
            gauge(f'TUI_PW_{screen_id}', screen_id, eq_type, (LEFT, top + BAR_TOP, PLAYER_CONTENT_WIDTH, BAR_HEIGHT),
                  fill, tint, track='TUI_PlayerTrack'),
        ]
    parts.append(gauge('TUI_PW_ZealTick', 'ZealTick', TICK_TYPE,
                       (LEFT, PLAYER_SECTIONS_TOP + PLAYER_SECTION_PITCH + MANA_TICK_TOP, PLAYER_CONTENT_WIDTH,
                        TICK_HEIGHT), 'TUI_TickFill', TICK_RGB))
    # XP/h and its % at the line's start, AA/h and its % ending at its end (see RATE_PAIR_WIDTH). The numbers
    # and their %s in the values' green. The drawn % needs a gauge above 0 to show: your own health, so it
    # always shows, 0% too.
    rates = []
    for item, caption, eq_type, left in (
            ('ExpPerHour', 'XP/h', XP_PER_HOUR_TYPE, LEFT),
            ('AAPerHour', 'AA/h', AA_PER_HOUR_TYPE, PLAYER_RIGHT - RATE_PAIR_WIDTH)):
        right = left + RATE_PAIR_WIDTH
        rate, readout = percent_readout(f'TUI_PW_{item}', f'TUI_PW_{item}Percent', eq_type, 1, PLAYER_XP_TOP, right,
                                        rgb=VALUE_RGB)
        rates.append(rate)
        number_x = right - PERCENT_WIDTH - NUMBER_WIDTH
        parts += [label(f'TUI_PW_{item}Caption', None, (left, PLAYER_XP_TOP, number_x - left, TEXT_HEIGHT),
                        caption, rgb=CAPTION_RGB), *readout]
    for c, (caption, eq_type) in enumerate(RESISTS):
        x = LEFT + c * PLAYER_CONTENT_WIDTH // len(RESISTS)
        width = LEFT + (c + 1) * PLAYER_CONTENT_WIDTH // len(RESISTS) - x
        parts.append(label(f'TUI_PW_{caption}Caption', None, (x, RESISTS_TOP, width, CAPTION_HEIGHT), caption,
                           rgb=CAPTION_RGB, font=CAPTION_FONT, align_center=True))
        parts.append(label(f'TUI_PW_{caption}', eq_type, (x, RESISTS_TOP + CAPTION_HEIGHT, width, TEXT_HEIGHT), '',
                           align_center=True, rgb=VALUE_RGB))
    parts += [hidden_gauge('TUI_PW_PlayerFatigue', 'PlayerFatigue', 3), hidden_gauge('TUI_PW_PetHP', 'PetHP', 16)]
    height = 2 * BORDER + RESISTS_TOP + CAPTION_HEIGHT + TEXT_HEIGHT + PLAYER_BOTTOM_GAP
    return window('PlayerWindow', 'Player', height, parts, width=PLAYER_WIDTH, inner=[*percents, *rates])


def buff_window():
    """Your effects: 15 slots, their names from the stock labels 45 to 59."""
    return effects_table('BuffWindow', 'Effects', 15, 45, 'TUI_BW')


def song_window():
    """Your songs and other short effects: 6 slots, their names from Zeal's labels 135 to 140."""
    return effects_table('ShortDurationBuffWindow', 'Songs', 6, 135, 'TUI_SDBW')


def spell_gem(name, screen_id, top):
    """A spell gem as wide as the window's inside and a row tall, so all of the row casts. The client draws
    its Holder or Background and the spell's icon over it, the icon a padding from the window's edges. Both
    are a clear row the gem's size: solid rows in the panel's color showed under each gem at a window Alpha
    below 255, drawn over the see-through panel a second time, and the user had them removed."""
    return node('SpellGem', [
        node('ScreenID', screen_id),
        node('RelativePosition', True),
        point('Location', 0, top),
        size(GEM_ROW_WIDTH, GEM_ROW_HEIGHT),
        node('SpellGemDrawTemplate', [node('Holder', 'TUI_GemSlot'), node('Background', 'TUI_GemSlot'),
                                      node('Highlight', 'TUI_Clear')]),
        node('SpellIconOffsetX', LEFT),
        node('SpellIconOffsetY', GEM_ICON_MARGIN),
    ], name)


def spell_bar_window():
    """Your spell gems as a table, a row each: the gem's icon, then the spell's name with Zeal's recast
    countdown under it, a divider under each row. Zeal's global recovery along the top, and the spellbook's
    toggle in a row of its own under the gems."""
    dividers, gems, names, recasts = [], [], [], []
    for n in range(GEM_COUNT):
        top = GEMS_TOP + n * GEM_ROW_PITCH
        dividers.append(picture(f'TUI_CSPW_Divider{n}', 'TUI_SpellBarDivider',
                                (LEFT, top + GEM_ROW_HEIGHT, SPELL_BAR_CONTENT_WIDTH, DIVIDER_HEIGHT)))
        gems.append(spell_gem(f'TUI_CSPW_Spell{n}', f'CSPW_Spell{n}', top))
        names.append(label(f'TUI_CSPW_Spell{n}_Name', GEM_NAME_TYPE + n,
                           (GEM_NAME_X, top + GEM_NAME_TOP, SPELL_BAR_RIGHT - GEM_NAME_X, TEXT_HEIGHT), '',
                           screen_id=f'CSPW_Spell{n}_Name'))
        recasts.append(gauge(f'TUI_CSPW_Spell{n}_Recast', f'CSPW_Spell{n}_Recast', RECAST_TYPE + n,
                             (GEM_NAME_X, top + RECAST_TOP, RECAST_WIDTH, TICK_HEIGHT), 'TUI_RecastFill', TEXT_RGB))
    recovery = gauge('TUI_CSPW_Global_Recast', 'CSPW_Global_Recast', CAST_RECOVERY_TYPE,
                     (LEFT, 0, SPELL_BAR_CONTENT_WIDTH, TICK_HEIGHT), 'TUI_CastRecoveryFill', SPELL_RGB)
    book = toggle_button('TUI_CSPW_SpellBook', 'CSPW_SpellBook', LEFT, BOOK_TOP, 'Opens and closes Your Spellbook',
                         'Book', BOOK_WIDTH)
    # The names and bars over the gems, which are solid, as duxaUI's names are over its gems.
    return window('CastSpellWnd', 'Spells', SPELL_BAR_HEIGHT, dividers + gems + names + recasts + [recovery, book],
                  tooltip='Allows you to cast your memorized spells', width=SPELL_BAR_WIDTH)


def hot_spot(column, row):
    """The top left of the hot button window's spot in that column and row, inside the frame."""
    return LEFT + column * HOT_PITCH, LEFT + row * HOT_PITCH


def inv_slot(name, screen_id, eq_type, spot, background, side=HOT_SIZE):
    """An item slot at spot, side square, showing background while it's empty. side 0 hides one the client looks
    up."""
    return node('InvSlot', [
        node('ScreenID', screen_id),
        node('RelativePosition', True),
        point('Location', *spot),
        size(side, side),
        node('Background', background),
        node('EQType', eq_type),
        node('Style_VScroll', False),
        node('Style_HScroll', False),
        node('Style_Transparent', False),
    ], name)


def hot_button_window():
    """duxaUI's hot button window in our look (see HOTBUTTON_FILE): the page arrows and number, the ten macros
    under them, two to a row, and beside them the weapon slots over the bag slots."""
    arrows = [icon_square(f'TUI_{screen_id}', screen_id, LEFT + n * (HOT_PAGE_WIDTH - ARROW_SIZE), LEFT, tooltip,
                          f'Hot{icon}', ARROW_SIZE, False, ICON_ART, HOT_SIZE)
              for n, (screen_id, tooltip, icon) in enumerate(HOT_ARROWS)]
    number_x = LEFT + ARROW_SIZE + BUTTON_GAP
    number = label(f'TUI_{HOT_PAGE_LABEL}', None,
                   (number_x, LEFT + HOT_PAGE_LABEL_TOP, HOT_PAGE_WIDTH - 2 * (ARROW_SIZE + BUTTON_GAP), TEXT_HEIGHT),
                   '1', screen_id=HOT_PAGE_LABEL, align_center=True)
    # Each macro's spot: the button, whose name the game writes, then the item slot and spell gem it shows
    # instead for an item's or a spell's hot button, all three the same size.
    buttons, items, gems = [], [], []
    for n in range(1, HOT_MACROS + 1):
        spot = hot_spot((n - 1) % 2, 1 + (n - 1) // 2)
        buttons.append(node('Button', [
            node('ScreenID', f'HB_Button{n}'),
            node('Font', MACRO_FONT),
            node('RelativePosition', True),
            point('Location', *spot),
            size(HOT_SIZE, HOT_SIZE),
            node('Style_Transparent', False),
            node('Style_Checkbox', False),
            node('Text', ''),
            color('TextColor', TEXT_RGB),
            # duxaUI and the stock skin give the macros a DecalSize, so ours has one too, the button's size.
            node('DecalSize', [node('CX', HOT_SIZE), node('CY', HOT_SIZE)]),
            node('ButtonDrawTemplate', [node(state, f'TUI_HotButton{BUTTON_ART[state]}') for state in BUTTON_STATES]),
        ], f'TUI_HB_Button{n}'))
        items.append(inv_slot(f'TUI_HB_InvSlot{n}', f'HB_InvSlot{n}', -1, spot, 'TUI_HotButtonNormal'))
        # The client draws a gem's Holder and Background under the spell's icon (see spell_gem()).
        gems.append(node('SpellGem', [
            node('ScreenID', f'HB_SpellGem{n}'),
            node('RelativePosition', True),
            point('Location', *spot),
            size(HOT_SIZE, HOT_SIZE),
            node('SpellGemDrawTemplate', [node('Holder', 'TUI_HotButtonNormal'),
                                          node('Background', 'TUI_HotButtonNormal'), node('Highlight', 'TUI_Clear')]),
            node('SpellIconOffsetX', HOT_GEM_OFFSET),
            node('SpellIconOffsetY', HOT_GEM_OFFSET),
        ], f'TUI_HB_SpellGem{n}'))
    slots = [inv_slot(f'TUI_HB_Slot{eq_type}', HOT_SLOT_IDS[c * HOT_ROWS + r], eq_type, hot_spot(2 + c, r),
                      f'TUI_HotSlot{icon}' if icon else 'TUI_HotButtonNormal')
             for c, column in enumerate(HOT_SLOTS) for r, (eq_type, icon) in enumerate(column)]
    # In duxaUI's order: the item slots and gems over the buttons, then the weapon and bag slots.
    return window('HotButtonWnd', 'Hot Buttons', HOT_HEIGHT, arrows + [number] + buttons + items + gems + slots,
                  tooltip='Hot Buttons', width=HOT_WIDTH)


def container_window():
    """A bag's window (see CONTAINER_FILE): its slots two across, then Done across the bottom, with Combine over it
    in a tradeskill container. The bag's name and icon are there, hidden, at the grid's top corners."""
    name = hidden_label('TUI_Bag_Label', 'Container_Label', *BAG_LABEL_SPOT)
    icon = hidden_button('TUI_Bag_Icon', 'Container_Icon', *BAG_ICON_SPOT)
    slots = [inv_slot(f'TUI_Bag_Slot{n}', f'ContainerSlot{n}', BAG_SLOT_TYPE + n - 1,
                      (BAG_LEFT + (n - 1) % BAG_COLUMNS * HOT_PITCH, BAG_TOP + (n - 1) // BAG_COLUMNS * HOT_PITCH),
                      'TUI_HotButtonNormal')
             for n in range(1, BAG_SLOTS + 1)]
    buttons = [anchored_button(f'TUI_Bag_{label_text}', screen_id, label_text, BAG_LEFT, bottom, BAG_CONTENT_WIDTH,
                               BUTTON_HEIGHT, layout_height)
               for screen_id, label_text, bottom, layout_height in BAG_BUTTONS]
    return window('ContainerWindow', 'Container', BAG_HEIGHT, [name, icon, *slots, *buttons], tooltip='Container',
                  width=BAG_WIDTH)


def raid_window():
    """The raid's players in a group, then those in none under a caption, each list's columns group, name, class
    and rank, and the raid's buttons under them in two rows of three (see RAID_FILE)."""
    grouped = listbox('TUI_RW_PlayerList', 'RAID_PlayerList', (LEFT, LEFT, RAID_LIST_WIDTH, RAID_GROUPED_HEIGHT),
                      'List of all players currently in your raid', RAID_COLUMNS)
    caption = label('TUI_RW_NotInGroupPlayerListLabel', None, (LEFT, RAID_CAPTION_TOP, RAID_LIST_WIDTH, TEXT_HEIGHT),
                    'Not in a group', screen_id='RAID_NotInGroupPlayerListLabel', rgb=CAPTION_RGB)
    ungrouped = listbox('TUI_RW_NotInGroupPlayerList', 'RAID_NotInGroupPlayerList',
                        (LEFT, RAID_UNGROUPED_TOP, RAID_LIST_WIDTH, RAID_UNGROUPED_HEIGHT),
                        'List of all players currently in your raid not in a group', RAID_COLUMNS)
    buttons = [button(f'TUI_RW_{screen_id}', screen_id, label_text,
                      LEFT + sum(RAID_BUTTON_WIDTHS[:column]) + column * BUTTON_GAP,
                      RAID_BUTTONS_TOP + row * (BUTTON_HEIGHT + BUTTON_ROW_GAP), RAID_BUTTON_WIDTHS[column],
                      tooltip=tooltip)
               for screen_id, label_text, tooltip, column, row in RAID_BUTTONS]
    hidden = [hidden_label(f'TUI_RW_{screen_id}', screen_id) for screen_id in RAID_HIDDEN_LABELS]
    return window('RaidWindow', 'Raid', RAID_HEIGHT, [grouped, caption, ungrouped, *buttons, *hidden],
                  width=RAID_WIDTH)


def merchant_window():
    """All 80 of a merchant's slots, eight across; under them a divider, then the considered item's square with
    Quarm's recharge group beside it, then Buy or Sell and Done (see MERCHANT_FILE). The merchant's name is there,
    hidden."""
    # The slots, in the client's panel for them: see-through on the window's panel, placed by Location and Size, so
    # Quarm's anchor change can't move its bottom.
    slots = [inv_slot(f'TUI_MW_Slot{n}', f'MW_MerchantSlot{n}', MERCHANT_SLOT_TYPE + n,
                      (n % MERCHANT_COLUMNS * HOT_PITCH, n // MERCHANT_COLUMNS * HOT_PITCH), 'TUI_HotButtonNormal')
             for n in range(MERCHANT_SLOTS)]
    panel = node('Screen', [
        node('ScreenID', 'MerchantSlotsWnd'),
        node('RelativePosition', True),
        point('Location', LEFT, LEFT),
        size(MERCHANT_CONTENT_WIDTH, MERCHANT_GRID_HEIGHT),
        node('Style_VScroll', False),
        node('Style_HScroll', False),
        node('Style_Transparent', True),
        node('DrawTemplate', FRAME_TEMPLATE),
        node('Style_Border', False),
    ] + [node('Pieces', slot[2]) for slot in slots], 'TUI_MW_SlotsWnd')
    # The divider under the grid: the Effects window's, at the content row's width.
    divider = picture('TUI_MW_Divider', 'TUI_MerchantDivider',
                      (LEFT, MERCHANT_DIVIDER_TOP, MERCHANT_CONTENT_WIDTH, DIVIDER_HEIGHT))
    # The considered item's square, the plain square with the item's icon on it, which the client sets.
    top = MERCHANT_BAND_TOP
    item = node('Button', [
        node('ScreenID', 'MW_SelectedItem'),
        node('RelativePosition', True),
        point('Location', LEFT, top),
        size(HOT_SIZE, HOT_SIZE),
        node('Style_Transparent', False),
        node('TooltipReference', 'Item being considered'),
        node('Style_Checkbox', False),
        node('ButtonDrawTemplate', [node('Normal', 'TUI_HotButtonNormal'), node('NormalDecal', ITEM_ICONS)]),
        point('DecalOffset', 0, 0),
        node('DecalSize', [node('CX', HOT_SIZE), node('CY', HOT_SIZE)]),
    ], 'TUI_MW_SelectedItem')
    text_top = top + MERCHANT_TEXT_TOP
    item_label = label(f'TUI_{MERCHANT_ITEM_LABEL}', None,
                       (MERCHANT_TEXT_X, text_top, MERCHANT_TEXT_WIDTH, len(MERCHANT_RECHARGE) * TEXT_HEIGHT), '',
                       screen_id=MERCHANT_ITEM_LABEL)
    recharge = [label(f'TUI_{screen_id}', None,
                      (MERCHANT_TEXT_X, text_top + line * TEXT_HEIGHT, MERCHANT_TEXT_WIDTH, TEXT_HEIGHT), '',
                      screen_id=screen_id)
                for screen_id, line in MERCHANT_RECHARGE]
    # No tooltip of ours: Quarm writes the price per charge there.
    recharge.append(button(f'TUI_{MERCHANT_RECHARGE_BUTTON}', MERCHANT_RECHARGE_BUTTON, '', MERCHANT_RECHARGE_X,
                           top + MERCHANT_RECHARGE_TOP, MERCHANT_BUTTON_WIDTHS[1], TEXT_BUTTON_HEIGHT,
                           font=ACTION_FONT, text='Recharge'))
    buttons = [button(f'TUI_MW_{screen_id}', screen_id, '',
                      LEFT + sum(MERCHANT_BUTTON_WIDTHS[:column]) + column * BUTTON_GAP, MERCHANT_BUTTONS_TOP,
                      MERCHANT_BUTTON_WIDTHS[column], TEXT_BUTTON_HEIGHT, tooltip=tooltip, font=ACTION_FONT,
                      text=button_name)
               for screen_id, button_name, tooltip, column in MERCHANT_BUTTONS]
    name = hidden_label('TUI_MW_MerchantName', 'MW_MerchantName')
    return window('MerchantWnd', 'Merchant', MERCHANT_HEIGHT,
                  [panel, divider, item, item_label, *recharge, *buttons, name], width=MERCHANT_WIDTH, inner=slots)


def confirmation_dialog():
    """The question or notice in up to three lines, with Yes and No under it, or OK alone in the middle, with a
    dialog's room inside (see CONFIRM_FILE)."""
    # Straight on the panel, like the raid lists: a clear template and nothing of its own drawn. SIDL gives an
    # STMLbox no text color, so the text is in the client's.
    text = node('STMLbox', [
        node('ScreenID', 'TextOutput'),
        node('Font', TEXT_FONT),
        node('RelativePosition', True),
        point('Location', DIALOG_LEFT, CONFIRM_TEXT_TOP),
        size(CONFIRM_CONTENT_WIDTH, CONFIRM_TEXT_LINES * TEXT_HEIGHT),
        node('Style_VScroll', False),
        node('Style_HScroll', False),
        node('Style_Transparent', True),
        node('Style_Border', False),
        node('DrawTemplate', EDIT_TEMPLATE),
    ], 'TUI_CD_TextOutput')
    # The Actions window's buttons: their names are their own text, in its font.
    buttons = [button(f'TUI_CD_{screen_id}', screen_id, '', x, CONFIRM_BUTTONS_TOP, width, TEXT_BUTTON_HEIGHT,
                      font=ACTION_FONT, text=name)
               for screen_id, name, x, width in CONFIRM_BUTTONS]
    # No name of ours: the stock window has none, and no title bar shows one.
    return window('ConfirmationDialogBox', None, CONFIRM_HEIGHT, [text, *buttons], width=CONFIRM_WIDTH)


def item_display_window():
    """The item's name on the title bar with the Close button, its icon in the top left corner and its text in a
    column to the icon's right (see ITEM_FILE). Only the stock window's two controls, in its order: Zeal links just
    those in its own item windows."""
    # Straight on the panel, like the raid lists, with our slim scrollbar. Anchored like every stock skin's, so a
    # window the game gives another size (the old sizable one's in the ini) still lays out.
    text = node('STMLbox', [
        node('ScreenID', 'ItemDescription'),
        node('Font', TEXT_FONT),
        node('DrawTemplate', EDIT_TEMPLATE),
        node('RelativePosition', True),
        node('Style_VScroll', True),
        node('Style_HScroll', False),
        node('Style_Transparent', True),
        *anchor_nodes((ITEM_TEXT_X, ITEM_TEXT_TOP, LEFT, LEFT), False),
        node('Style_Border', False),
    ], 'TUI_IDW_ItemDescription')
    # The game makes an item's icon the button's Normal art and a spell's its decal, both 40px (see ITEM_FILE); the
    # XML's are what the stock window has, never shown.
    icon = node('Button', [
        node('ScreenID', 'IconButton'),
        node('RelativePosition', True),
        *anchor_nodes((LEFT, PADDING, LEFT + ITEM_ICON, PADDING + ITEM_ICON), False, right_from_left=True,
                      bottom_from_top=True),
        node('Style_VScroll', False),
        node('Style_HScroll', False),
        node('Style_Transparent', False),
        node('Style_Checkbox', False),
        node('ButtonDrawTemplate', [node('Normal', 'TUI_Clear'), node('NormalDecal', BUFF_ICONS)]),
        point('DecalOffset', 0, 0),
        node('DecalSize', [node('CX', ITEM_ICON), node('CY', ITEM_ICON)]),
    ], 'TUI_IDW_IconButton')
    # The game writes the item's name over "Item Display", its own placeholder, in the window's font.
    return window('ItemDisplayWindow', 'Item Display', ITEM_HEIGHT, [text, icon],
                  tooltip='This is an Item Display window', width=ITEM_WIDTH, template=ITEM_TEMPLATE, title_bar=True,
                  font=TEXT_FONT, close_box=True)


def quantity_window():
    """How many of a stack to take: the item window's title bar with the window's name on its left and Close, the
    slider across the window, and under it the number field and Accept side by side, with a dialog's room inside (see
    QUANTITY_FILE)."""
    slider = node('Slider', [
        node('ScreenID', 'QTYW_Slider'),
        node('RelativePosition', True),
        point('Location', DIALOG_LEFT, QUANTITY_SLIDER_TOP),
        size(QUANTITY_CONTENT_WIDTH, SLIDER_HEIGHT),
        node('SliderArt', SLIDER_TEMPLATE),
    ], 'TUI_QTYW_Slider')
    # The field as the chat input's: a child window drawing the strip, and the see-through number box on it, inset
    # FIELD_PADDING each side.
    width = QUANTITY_ROW_WIDTHS[0]
    strip = node('Screen', [
        node('RelativePosition', True),
        point('Location', DIALOG_LEFT, QUANTITY_ROW_TOP),
        size(width, INPUT_HEIGHT),
        node('DrawTemplate', FIELD_TEMPLATE),
        node('Style_Transparent', False),
        node('Style_Border', True),
    ], 'TUI_QTYW_Field')
    number = node('Editbox', [
        node('ScreenID', 'QTYW_SliderInput'),
        node('Font', TEXT_FONT),
        node('DrawTemplate', EDIT_TEMPLATE),
        node('RelativePosition', True),
        point('Location', DIALOG_LEFT + FIELD_PADDING, QUANTITY_ROW_TOP),
        size(width - 2 * FIELD_PADDING, INPUT_HEIGHT),
        node('Style_Border', False),
        node('Style_Transparent', True),
        color('TextColor', TEXT_RGB),
    ], 'TUI_QTYW_SliderInput')
    # The confirmation dialog's button: its name its own text, in the Actions window's font.
    accept = button('TUI_QTYW_Accept_Button', 'QTYW_Accept_Button', '', QUANTITY_ACCEPT_X, QUANTITY_ROW_TOP,
                    QUANTITY_ROW_WIDTHS[1], TEXT_BUTTON_HEIGHT, font=ACTION_FONT, text='Accept')
    # No title for the game to write: the name is in the bar's art (see QUANTITY_TITLE_INK).
    return window('QuantityWnd', None, QUANTITY_HEIGHT, [slider, strip, number, accept], width=QUANTITY_WIDTH,
                  template=QUANTITY_TEMPLATE, title_bar=True, close_box=True)


def coin_box(name, screen_id, caption, x, y, tooltip=COIN_TOOLTIP, lit=True, width=COIN_WIDTH, art='Coin'):
    """A box the game writes an amount of one coin on (see COIN_CAPTIONS), width x COIN_HEIGHT at x, y, and then its
    coin's name as a label over it. lit gives the box the buttons' hovered and pressed looks, for your own coins, which
    take a drop; without it the box keeps its resting look, like a slot. art names the box's art at that width."""
    children = [
        node('ScreenID', screen_id),
        node('Font', TEXT_FONT),
        node('RelativePosition', True),
        point('Location', x, y),
        size(width, COIN_HEIGHT),
        node('Style_Transparent', False),
    ]
    if tooltip:
        children.append(node('TooltipReference', tooltip))
    box = node('Button', children + [
        node('Style_Checkbox', False),
        node('Text', ''),  # the game writes the amount
        color('TextColor', TEXT_RGB),
        node('ButtonDrawTemplate', [node(state, f'TUI_{art}{BUTTON_ART[state] if lit else "Normal"}')
                                    for state in BUTTON_STATES]),
    ], name)
    caption_box = (x + PADDING, y + COIN_CAPTION_TOP, COIN_CAPTION_WIDTH, TEXT_HEIGHT)
    return [box, label(f'{name}_Caption', None, caption_box, caption)]


def vertical_divider(name, x, y, height):
    """The row divider standing up, height tall at x, y: a child window drawing only its background (see
    DIVIDER_TEMPLATE)."""
    return node('Screen', [
        node('RelativePosition', True),
        point('Location', x, y),
        size(DIVIDER_HEIGHT, height),
        node('Style_VScroll', False),
        node('Style_HScroll', False),
        node('Style_Transparent', False),
        node('DrawTemplate', DIVIDER_TEMPLATE),
        node('Style_Border', False),
    ], name)


def give_window():
    """What you hand an NPC: its name, then your four item slots in a row on the hot bar's squares, the coin boxes two
    across under them, a divider, and Give and Cancel (see GIVE_FILE)."""
    name = label('TUI_GVW_NPCName', None, (LEFT, GIVE_NAME_TOP, GIVE_CONTENT_WIDTH, TEXT_HEIGHT), '',
                 screen_id='GVW_NPCName')
    slots = [inv_slot(f'TUI_GVW_MyItemSlot{n}', f'GVW_MyItemSlot{n}', GIVE_SLOT_TYPE + n,
                      (LEFT + n % GIVE_SLOT_COLUMNS * HOT_PITCH, GIVE_SLOTS_TOP + n // GIVE_SLOT_COLUMNS * HOT_PITCH),
                      'TUI_HotButtonNormal')
             for n in range(GIVE_SLOTS)]
    coins = [part for n, (screen_id, caption) in enumerate(GIVE_COINS)
             for part in coin_box(f'TUI_GVW_{screen_id}', screen_id, caption,
                                  LEFT + n % GIVE_COIN_COLUMNS * (COIN_WIDTH + BUTTON_GAP),
                                  GIVE_COINS_TOP + n // GIVE_COIN_COLUMNS * (COIN_HEIGHT + BUTTON_ROW_GAP))]
    # The Effects window's divider, at the content row's width.
    divider = picture('TUI_GVW_Divider', 'TUI_GiveDivider', (LEFT, GIVE_DIVIDER_TOP, GIVE_CONTENT_WIDTH, DIVIDER_HEIGHT))
    buttons = [button(f'TUI_GVW_{screen_id}', screen_id, '',
                      LEFT + sum(GIVE_HALF_WIDTHS[:column]) + column * BUTTON_GAP, GIVE_BUTTONS_TOP,
                      GIVE_HALF_WIDTHS[column], TEXT_BUTTON_HEIGHT, font=ACTION_FONT, text=button_name)
               for screen_id, button_name, column in GIVE_BUTTONS]
    return window('GiveWnd', 'Give', GIVE_HEIGHT, [name, *slots, *coins, divider, *buttons], width=GIVE_WIDTH)


def trade_window():
    """Their side on the left and yours on the right with a divider between them, each its name, then its eight slots
    two across and its coin boxes under them; a divider across, and Trade and Cancel under it (see TRADE_FILE)."""
    parts = [vertical_divider('TUI_TRDW_Divider', TRADE_DIVIDER_X, TRADE_DIVIDER_TOP, TRADE_DIVIDER_HEIGHT)]
    for prefix, x, first in TRADE_SIDES:
        # The game writes the name, centered over its side like the stock window's.
        parts.append(label(f'TUI_TRDW_{prefix}Name', None, (x, TRADE_NAME_TOP, TRADE_SIDE_WIDTH, TEXT_HEIGHT), '',
                           screen_id=f'TRDW_{prefix}Name', align_center=True))
        parts += [inv_slot(f'TUI_TRDW_TradeSlot{first + n}', f'TRDW_TradeSlot{first + n}', TRADE_SLOT_TYPE + first + n,
                           (x + n // TRADE_SLOT_ROWS * HOT_PITCH, TRADE_SLOTS_TOP + n % TRADE_SLOT_ROWS * HOT_PITCH),
                           'TUI_HotButtonNormal')
                  for n in range(TRADE_SLOTS)]
        # Only your own coins take a drop, so theirs keep their resting look under the pointer, with no tooltip.
        yours = prefix == 'My'
        parts += [part for n, caption in enumerate(COIN_CAPTIONS)
                  for part in coin_box(f'TUI_TRDW_{prefix}Money{n}', f'TRDW_{prefix}Money{n}', caption, x,
                                       TRADE_COINS_TOP + n * (COIN_HEIGHT + BUTTON_ROW_GAP),
                                       tooltip=COIN_TOOLTIP if yours else None, lit=yours)]
    # The give window's divider, at this content row's width.
    parts.append(picture('TUI_TRDW_RowDivider', 'TUI_TradeDivider',
                         (LEFT, TRADE_ROW_DIVIDER_TOP, TRADE_CONTENT_WIDTH, DIVIDER_HEIGHT)))
    parts += [button(f'TUI_TRDW_{screen_id}', screen_id, '',
                     LEFT + sum(TRADE_BUTTON_WIDTHS[:column]) + column * BUTTON_GAP, TRADE_BUTTONS_TOP,
                     TRADE_BUTTON_WIDTHS[column], TEXT_BUTTON_HEIGHT, font=ACTION_FONT, text=button_name)
              for screen_id, button_name, column in TRADE_BUTTONS]
    return window('TradeWnd', 'Trade', TRADE_HEIGHT, parts, width=TRADE_WIDTH)


def loot_window():
    """A corpse's name along the top, then all 30 of its slots six across on the hot bar's squares, and Link All, Loot
    All and Done along the bottom (see LOOT_FILE)."""
    name = label('TUI_LW_CorpseName', None, (LEFT, LOOT_NAME_TOP, LOOT_CONTENT_WIDTH, TEXT_HEIGHT), '',
                 screen_id='LW_CorpseName')
    # The slots in the client's panel for them, see-through on the window's panel, as the merchant's are.
    slots = [inv_slot(f'TUI_LW_LootSlot{n}', f'LW_LootSlot{n}', LOOT_SLOT_TYPE + n,
                      (n % LOOT_COLUMNS * HOT_PITCH, n // LOOT_COLUMNS * HOT_PITCH), 'TUI_HotButtonNormal')
             for n in range(LOOT_SLOTS)]
    panel = node('Screen', [
        node('ScreenID', 'LootInvWnd'),
        node('RelativePosition', True),
        point('Location', LEFT, LOOT_SLOTS_TOP),
        size(LOOT_CONTENT_WIDTH, LOOT_GRID_HEIGHT),
        node('Style_VScroll', False),
        node('Style_HScroll', False),
        node('Style_Transparent', True),
        node('DrawTemplate', FRAME_TEMPLATE),
        node('Style_Border', False),
    ] + [node('Pieces', slot[2]) for slot in slots], 'TUI_LW_LootInvWnd')
    buttons = [button(f'TUI_LW_{screen_id}', screen_id, '',
                      LEFT + sum(LOOT_BUTTON_WIDTHS[:column]) + column * BUTTON_GAP, LOOT_BUTTONS_TOP,
                      LOOT_BUTTON_WIDTHS[column], TEXT_BUTTON_HEIGHT, font=ACTION_FONT, text=button_name)
               for screen_id, button_name, column in LOOT_BUTTONS]
    return window('LootWnd', 'Loot', LOOT_HEIGHT, [name, panel, *buttons], width=LOOT_WIDTH, inner=slots)


def bank_window():
    """The shared bank's ten slots on the left under their caption, with Change and Done under them; the bank's 30 on
    the right under the banker's name, with its coin boxes under them; a divider standing between (see BANK_FILE)."""
    parts = [vertical_divider('TUI_BW_Divider', BANK_DIVIDER_X, BANK_DIVIDER_TOP, BANK_DIVIDER_HEIGHT)]
    # The game writes the banker's name, from the left like the give window's NPC; nothing writes the caption.
    parts.append(label('TUI_BW_BankerName', None, (BANK_X, BANK_NAME_TOP, BANK_CONTENT_WIDTH, TEXT_HEIGHT), '',
                       screen_id='BW_BankerName'))
    parts.append(label('TUI_BW_SharedBankLabel', None, (LEFT, BANK_NAME_TOP, SHARED_WIDTH, TEXT_HEIGHT),
                       SHARED_CAPTION, screen_id='BW_SharedBankLabel'))
    for prefix, x, slots, first_type in (('SharedBank', LEFT, SHARED_SLOTS, SHARED_SLOT_TYPE),
                                         ('Bank', BANK_X, BANK_SLOTS, BANK_SLOT_TYPE)):
        parts += [inv_slot(f'TUI_BW_{prefix}Slot{n}', f'BW_{prefix}Slot{n}', first_type + n,
                           (x + n // BANK_ROWS * HOT_PITCH, BANK_SLOTS_TOP + n % BANK_ROWS * HOT_PITCH),
                           'TUI_HotButtonNormal')
                  for n in range(slots)]
    parts += [part for n, (screen_id, caption, tooltip) in enumerate(BANK_COINS)
              for part in coin_box(f'TUI_BW_{screen_id}', screen_id, caption,
                                   BANK_X + n % BANK_COIN_COLUMNS * (BANK_COIN_WIDTH + BUTTON_GAP),
                                   BANK_BAND_TOP + n // BANK_COIN_COLUMNS * (COIN_HEIGHT + BUTTON_ROW_GAP),
                                   tooltip=tooltip, width=BANK_COIN_WIDTH, art='BankCoin')]
    parts += [button(f'TUI_BW_{screen_id}', screen_id, '', LEFT,
                     BANK_BAND_TOP + row * (TEXT_BUTTON_HEIGHT + BUTTON_ROW_GAP), SHARED_WIDTH, TEXT_BUTTON_HEIGHT,
                     font=ACTION_FONT, text=button_name)
              for screen_id, button_name, row in BANK_BUTTONS]
    return window('BankWnd', 'Bank', BANK_HEIGHT, parts, width=BANK_WIDTH)


def skills_window():
    """Your skills in one list, name and value with the rank hidden, and Done under it (see SKILLS_FILE)."""
    skills = listbox('TUI_SKLW_SkillList', 'SkillList', (LEFT, LEFT, SKILLS_LIST_WIDTH, SKILLS_LIST_HEIGHT), None,
                     SKILLS_COLUMNS)
    done = button('TUI_SKLW_DoneButton', 'DoneButton', '', LEFT, SKILLS_DONE_TOP, SKILLS_LIST_WIDTH,
                  TEXT_BUTTON_HEIGHT, font=ACTION_FONT, text='Done')
    return window('SkillsWindow', 'Skills', SKILLS_HEIGHT, [skills, done], width=SKILLS_WIDTH)


def compass_window():
    """The eight directions on a strip the game slides past a soft red pointer as you turn, in the stock window's
    pieces and size (see COMPASS_FILE). The strips sit at the inside's left, as in the stock file, wider than the window:
    the game moves them and draws only what's inside. Nothing in it takes a click, so it drags by any part."""
    strips = [picture(f'TUI_Compass_Strip{n}', 'TUI_CompassStrip', (0, 0, COMPASS_STRIP_WIDTH, COMPASS_INSIDE_HEIGHT),
                      screen_id) for n, screen_id in enumerate(COMPASS_STRIPS, 1)]
    overlay = picture('TUI_Compass_Overlay', 'TUI_CompassOverlay', (0, 0, COMPASS_INSIDE_WIDTH, COMPASS_INSIDE_HEIGHT),
                      'CompassOverlay')
    return window('CompassWindow', None, COMPASS_HEIGHT, [*strips, overlay], width=COMPASS_WIDTH)


def spellbook_window():
    """Two pages of spells side by side, each eight of the spell bar's rows (the spell's icon, then its name), the
    memorizing and scribing bar along the top, and the page arrows, page numbers and Done along the bottom (see
    SPELLBOOK_FILE)."""
    bar_rect = (LEFT, BOOK_BAR_TOP, BOOK_CONTENT_WIDTH, TICK_HEIGHT)
    parts = [gauge('TUI_SBW_Memorize', 'SBW_Memorize_Gauge', MEMORIZE_TYPE, bar_rect, 'TUI_MemorizeFill', SPELL_RGB),
             gauge('TUI_SBW_Scribe', 'SBW_Scribe_Gauge', SCRIBE_TYPE, bar_rect, 'TUI_MemorizeFill', SPELL_RGB)]
    divider_top = BOOK_BAR_TOP + TICK_HEIGHT + PADDING
    parts.append(vertical_divider('TUI_SBW_Divider', BOOK_DIVIDER_X, divider_top, BOOK_LAST_DIVIDER_TOP - divider_top))
    parts += [picture(f'TUI_SBW_Divider{p}_{r}', 'TUI_BookRowDivider',
                      (x, BOOK_ROWS_TOP + r * GEM_ROW_PITCH + GEM_ROW_HEIGHT, BOOK_PAGE_WIDTH, DIVIDER_HEIGHT))
              for p, x in enumerate(BOOK_PAGE_XS) for r in range(BOOK_PAGE_ROWS - 1)]
    parts.append(picture('TUI_SBW_LastDivider', 'TUI_BookDivider',
                         (LEFT, BOOK_LAST_DIVIDER_TOP, BOOK_CONTENT_WIDTH, DIVIDER_HEIGHT)))
    # Spells 0 to 7 down the left page and 8 to 15 down the right, the stock reading order. Each slot is its whole row,
    # from BOOK_ICON_X before the icon, so a click anywhere on it counts; the client puts the spell's icon in the decal
    # and may paint the slot BlueIconBackground or A_SpellBookSlot, both clear, or RedIconBackground, whose bars fall
    # under the icon. The names go over the slots, as in the spell bar.
    spots = [(BOOK_PAGE_XS[n // BOOK_PAGE_ROWS], BOOK_ROWS_TOP + n % BOOK_PAGE_ROWS * GEM_ROW_PITCH)
             for n in range(BOOK_SPELLS)]
    parts += [node('Button', [
        node('ScreenID', f'SBW_Spell{n}'),
        node('RelativePosition', True),
        point('Location', x - BOOK_ICON_X, y + GEM_ICON_MARGIN - BOOK_ICON_Y),
        size(BOOK_SLOT_WIDTH, BOOK_SLOT_HEIGHT),
        node('Style_Transparent', False),
        node('Style_Checkbox', False),
        node('ButtonDrawTemplate', [node('Normal', 'TUI_BookSlot'), node('NormalDecal', BUFF_ICONS)]),
        point('DecalOffset', BOOK_ICON_X, BOOK_ICON_Y),
        node('DecalSize', [node('CX', GEM_ICON), node('CY', GEM_ICON)]),
    ], f'TUI_SBW_Spell{n}') for n, (x, y) in enumerate(spots)]
    parts += [static_text(f'TUI_SBW_SpellName{n}', f'SBW_SpellName{n}',
                          (x + GEM_ICON + PADDING, y + GEM_NAME_TOP, BOOK_NAME_WIDTH, TEXT_HEIGHT))
              for n, (x, y) in enumerate(spots)]
    parts += [icon_button(f'TUI_{screen_id}', screen_id, x, BOOK_BAND_TOP, tooltip, icon, ARROW_SIZE)
              for x, (screen_id, tooltip, icon) in zip((LEFT, BOOK_RIGHT - ARROW_SIZE), BOOK_ARROWS)]
    number_top = BOOK_BAND_TOP + SOCIAL_PAGE_LABEL_TOP  # the digits' ink centered on the band, as between the arrows
    parts += [static_text('TUI_SBW_LeftPageNum', 'SBW_LeftPageNum',
                          (LEFT + ARROW_SIZE + PADDING, number_top, NUMBER_WIDTH, TEXT_HEIGHT)),
              static_text('TUI_SBW_RightPageNum', 'SBW_RightPageNum',
                          (BOOK_RIGHT - ARROW_SIZE - PADDING - NUMBER_WIDTH, number_top, NUMBER_WIDTH, TEXT_HEIGHT),
                          align_right=True)]
    parts.append(button('TUI_SBW_DoneButton', 'DoneButton', '', LEFT + (BOOK_CONTENT_WIDTH - BOOK_DONE_WIDTH) // 2,
                        BOOK_BAND_TOP, BOOK_DONE_WIDTH, TEXT_BUTTON_HEIGHT, font=ACTION_FONT, text='Done'))
    parts += [hidden_button(f'TUI_{screen_id}', screen_id)
              for screen_id in ('SBW_MemPage0_Button', 'SBW_MemPage1_Button')]
    return window('SpellBookWnd', 'Spell Book', SPELLBOOK_HEIGHT, parts, tooltip='Your Spell Book',
                  width=SPELLBOOK_WIDTH)


def inventory_window():
    """The worn slots around a middle showing who you are and your XP and AA, where a dropped item is equipped; your
    stats, AC, ATK and weight and your coins in a column on the right, a divider between; the buttons along the bottom
    (see INVENTORY_FILE). The bag slots, the class picture, HP and the resists are there, hidden."""
    # First, so the middle's text draws over it: labels let clicks through, so a drop on the text reaches it too.
    parts = [node('Screen', [
        node('ScreenID', 'IW_CharacterView'),
        node('RelativePosition', True),
        point('Location', INV_MIDDLE_X, INV_MIDDLE_TOP),
        size(INV_MIDDLE_WIDTH, INV_MIDDLE_HEIGHT),
        node('Style_VScroll', False),
        node('Style_HScroll', False),
        node('Style_Transparent', False),
        node('TooltipReference', INV_DROP_TOOLTIP),
        node('DrawTemplate', EDIT_TEMPLATE),
        node('Style_Border', False),
    ], 'TUI_IW_CharacterView')]
    parts += [inv_slot(f'TUI_IW_InvSlot{eq_type}', f'InvSlot{eq_type}', eq_type,
                       (LEFT + half * HOT_PITCH // 2, LEFT + row * HOT_PITCH), f'TUI_HotSlot{icon}')
              for eq_type, icon, half, row in INV_WORN]
    parts += [inv_slot(f'TUI_IW_InvSlot{eq_type}', f'InvSlot{eq_type}', eq_type, (0, 0), 'TUI_Clear', side=0)
              for eq_type in INV_BAG_TYPES]
    # The middle: the level right-aligned against the class; XP and AA each a caption, its % in the bars' golden yellow
    # (the user: the values' green didn't suit it) and the bar under it. The drawn % needs a gauge above 0 to show: your
    # own health, so it always shows, 0% too.
    x, right = INV_MIDDLE_X, INV_MIDDLE_RIGHT
    class_x = x + INV_LEVEL_WIDTH + SPACE_WIDTH
    parts += [
        label('TUI_IW_Name', 1, (x, INV_WHO_TOP, INV_MIDDLE_WIDTH, TEXT_HEIGHT), '', screen_id='NameLabel'),
        label('TUI_IW_Level', 2, (x, INV_WHO_TOP + TEXT_HEIGHT, INV_LEVEL_WIDTH, TEXT_HEIGHT), '', align_right=True,
              screen_id='LevelClassLabel'),
        label('TUI_IW_Class', 3, (class_x, INV_WHO_TOP + TEXT_HEIGHT, right - class_x, TEXT_HEIGHT), ''),
        label('TUI_IW_Deity', 4, (x, INV_WHO_TOP + 2 * TEXT_HEIGHT, INV_MIDDLE_WIDTH, TEXT_HEIGHT), '',
              screen_id='DeityLabel', rgb=PET_RGB),
    ]
    percents = []
    readout_x = right - PERCENT_WIDTH - NUMBER_WIDTH
    for caption_id, caption, percent_type, gauge_id, gauge_type, top in INV_PROGRESS:
        percent, readout = percent_readout(f'TUI_IW_{caption}Percent', f'TUI_IW_{caption}PercentSign', percent_type,
                                           1, top, right, rgb=GOLD_RGB)
        percents.append(percent)
        parts += [
            label(f'TUI_IW_{caption}Caption', None, (x, top, readout_x - x, TEXT_HEIGHT), caption, screen_id=caption_id),
            *readout,
            gauge(f'TUI_IW_{caption}Bar', gauge_id, gauge_type, (x, top + BAR_TOP, INV_MIDDLE_WIDTH, BAR_HEIGHT),
                  'TUI_InvFill', GOLD_RGB, track='TUI_InvTrack'),
        ]
    # The column: the stats, then AC and ATK, then the weight as the player window's current/max, a divider across over
    # each of the last two, every value in the game's green ending at the column's right; the coins at its foot.
    parts.append(vertical_divider('TUI_IW_Divider', INV_DIVIDER_X, LEFT, INV_DOLL_HEIGHT))
    parts += [picture(name, 'TUI_InvDivider', (INV_COLUMN_X, top, INV_COLUMN_WIDTH, DIVIDER_HEIGHT))
              for name, top in INV_COLUMN_DIVIDERS]
    max_x = INV_RIGHT - PLAYER_NUMBER_WIDTH
    # The weight's numbers each in room for three digits (the max is about your STR), both right-aligned, so the max
    # ends at the column's right like every value above it (the user: left-aligned, it stopped short).
    weight_max_x = INV_RIGHT - NUMBER_WIDTH
    slash_x = weight_max_x - PLAYER_SLASH_WIDTH
    current_x = slash_x - NUMBER_WIDTH
    lines = [(caption, eq_type, INV_STATS_TOP + n * TEXT_HEIGHT) for n, (caption, eq_type) in enumerate(INV_STATS)]
    lines += [(caption, eq_type, INV_NUMBERS_TOP + n * TEXT_HEIGHT) for n, (caption, eq_type) in enumerate(INV_NUMBERS)]
    for caption, eq_type, top in lines:
        parts += [
            label(f'TUI_IW_{caption}', None, (INV_COLUMN_X, top, max_x - INV_COLUMN_X, TEXT_HEIGHT), caption,
                  screen_id=f'{caption}Label'),
            label(f'TUI_IW_{caption}Number', eq_type, (max_x, top, PLAYER_NUMBER_WIDTH, TEXT_HEIGHT), '',
                  align_right=True, screen_id=f'{caption}NumberLabel', rgb=VALUE_RGB),
        ]
    parts += [
        label('TUI_IW_Weight', None, (INV_COLUMN_X, INV_WEIGHT_TOP, current_x - INV_COLUMN_X, TEXT_HEIGHT), 'Weight',
              screen_id='WeightLabel'),
        label('TUI_IW_WeightCurrent', 24, (current_x, INV_WEIGHT_TOP, NUMBER_WIDTH, TEXT_HEIGHT), '',
              align_right=True, screen_id='WeightNumberLabel', rgb=VALUE_RGB),
        label('TUI_IW_WeightSlash', None, (slash_x, INV_WEIGHT_TOP, PLAYER_SLASH_WIDTH, TEXT_HEIGHT), '/',
              align_center=True),
        label('TUI_IW_WeightMax', 25, (weight_max_x, INV_WEIGHT_TOP, NUMBER_WIDTH, TEXT_HEIGHT), '', align_right=True,
              rgb=VALUE_RGB),
    ]
    parts += [part for n, caption in enumerate(COIN_CAPTIONS)
              for part in coin_box(f'TUI_IW_Money{n}', f'IW_Money{n}', caption, INV_COLUMN_X,
                                   INV_COINS_TOP + n * INV_COIN_PITCH, tooltip=None, width=INV_COLUMN_WIDTH,
                                   art='BankCoin')]
    parts += [button(f'TUI_IW_{screen_id}', screen_id, '', LEFT + sum(INV_BUTTON_WIDTHS[:column]) + column * BUTTON_GAP,
                     INV_BUTTONS_TOP, INV_BUTTON_WIDTHS[column], TEXT_BUTTON_HEIGHT, font=ACTION_FONT, text=button_name)
              for screen_id, button_name, column in INV_BUTTONS]
    parts += [hidden_label(f'TUI_IW_{screen_id}', screen_id) for screen_id in (*INV_HIDDEN_LABELS, INV_HIDDEN_AA[0])]
    parts.append(hidden_gauge('TUI_IW_AltAdvGauge', INV_HIDDEN_AA[1], 5))
    # With no size, the class picture shows nothing. When the window opens, the client puts the class's picture
    # (A_ClassAnim%02d) into the animation ClassAnim names, not just into ClassAnim: on the shared TUI_Clear, it showed
    # stretched over every control drawn with TUI_Clear (the spell gems, the chat input) in game. So it has its own.
    parts.append(picture('TUI_IW_ClassAnim', 'TUI_ClassAnim', (0, 0, 0, 0), screen_id='ClassAnim'))
    return window('InventoryWindow', 'Inventory', INV_HEIGHT, parts, tooltip='Inventory', width=INV_WIDTH,
                  inner=percents)


def tracking_window():
    """The con-color filters in a row, the Sort and Players dropdowns with their captions, the list of what's in range
    and Track and Cancel under it (see TRACKING_FILE). The "Filters" caption is there, hidden."""
    parts = [filter_toggle(f'TUI_{screen_id}', screen_id, LEFT + n * (FILTER_SIZE + BUTTON_GAP), FILTER_TOP, tooltip,
                           color_name)
             for n, (screen_id, color_name, tooltip, _) in enumerate(TRACK_FILTERS)]
    parts.append(listbox('TUI_TRW_TrackingList', 'TRW_TrackingList',
                         (LEFT, TRACK_LIST_TOP, TRACK_CONTENT_WIDTH, TRACK_LIST_HEIGHT), None, TRACK_COLUMNS))
    parts += [label(f'TUI_{caption_id}', None, (LEFT, top + TRACK_CAPTION_DROP, TRACK_CAPTION_WIDTH, TEXT_HEIGHT),
                    caption, screen_id=caption_id, rgb=CAPTION_RGB)
              for caption_id, caption, _, top, _ in TRACK_COMBOS]
    parts += [button(f'TUI_TRW_{screen_id.split("TRW_")[-1]}', screen_id, '',
                     LEFT + sum(TRACK_BUTTON_WIDTHS[:n]) + n * BUTTON_GAP,
                     TRACK_BUTTONS_TOP, TRACK_BUTTON_WIDTHS[n], TEXT_BUTTON_HEIGHT, font=ACTION_FONT, text=button_name)
              for n, (screen_id, button_name) in enumerate(TRACK_BUTTONS)]
    # The dropdowns last, Players then Sort, as in the stock window, so an open one lies over everything else: Sort's
    # over the Players box, both over the list.
    parts += [combobox(f'TUI_{combo_id}', combo_id, (TRACK_COMBO_X, top, TRACK_COMBO_WIDTH, COMBO_HEIGHT), choices)
              for _, _, combo_id, top, choices in reversed(TRACK_COMBOS)]
    parts.append(hidden_label('TUI_TRW_FiltersLabel', 'TRW_FiltersLabel'))
    return window('TrackingWnd', 'Tracking', TRACK_HEIGHT, parts, width=TRACK_WIDTH)


def aa_window():
    """The five stock tabs, each over its list of abilities, a divider under them, the selected ability's description
    under the list, and the column beside them: your AA XP, how much of your XP goes to AA, your points and the reuse
    timer, and Train, Hotkey and Done (see AA_FILE). A list's position is from its page's top left, which the tab box
    puts a padding under the divider and in from the window's left (see TAB_BORDER)."""
    inner = []
    for screen_id, list_id, _, art in AA_PAGES:
        abilities = listbox(f'TUI_AAW_{list_id}', list_id, (0, 0, AA_LIST_WIDTH, AA_LIST_HEIGHT), None, AA_COLUMNS)
        inner += [abilities, page(f'TUI_AAW_{screen_id}', screen_id, None, art, [abilities])]
    tabs = node('TabBox', [
        node('ScreenID', 'Subwindows'),
        node('Font', TEXT_FONT),  # its height + 8 is the least tab row, which our tabs are taller than
        node('RelativePosition', True),
        point('Location', 0, 0),
        size(AA_TAB_BOX_WIDTH, AA_TAB_BOX_HEIGHT),
        node('TabBorderTemplate', TAB_BORDER),
        node('PageBorderTemplate', PAGE_BORDER),
    ] + [node('Pages', f'TUI_AAW_{screen_id}') for screen_id, *_ in AA_PAGES], 'TUI_AAW_Tabs')
    parts = [tabs] + [picture(f'TUI_AAW_{name}', 'TUI_AADivider', (LEFT, top, AA_LIST_WIDTH, DIVIDER_HEIGHT))
                      for name, top in (('TabDivider', TAB_DIVIDER_TOP), ('ListDivider', AA_DIVIDER_TOP))]
    # Straight on the panel, like the item window's text, with our slim scrollbar.
    parts.append(node('STMLbox', [
        node('ScreenID', 'Description'),
        node('Font', TEXT_FONT),
        node('RelativePosition', True),
        point('Location', LEFT, AA_DESCRIPTION_TOP),
        size(AA_LIST_WIDTH, AA_DESCRIPTION_LINES * TEXT_HEIGHT),
        node('Style_VScroll', True),
        node('Style_HScroll', False),
        node('Style_Transparent', True),
        node('Style_Border', False),
        node('DrawTemplate', EDIT_TEMPLATE),
    ], 'TUI_AAW_Description'))
    # The column. The drawn % needs a gauge above 0 to show: your own health, so it always shows, 0% too. The bar is as
    # wide as the inventory's, so they share its art.
    x, right = AA_COLUMN_X, AA_RIGHT
    parts.append(vertical_divider('TUI_AAW_Divider', AA_DIVIDER_X, LEFT, AA_BOTTOM - LEFT))
    percent, readout = percent_readout('TUI_AAW_XPPercent', 'TUI_AAW_XPPercentSign', 27, 1, AA_XP_TOP, right,
                                       rgb=GOLD_RGB)
    readout_x = right - PERCENT_WIDTH - NUMBER_WIDTH
    parts += [
        label('TUI_AAW_XPCaption', None, (x, AA_XP_TOP, readout_x - x, TEXT_HEIGHT), 'AA XP'),
        *readout,
        gauge('TUI_AAW_ExpGauge', 'ExpGauge', 5, (x, AA_XP_TOP + BAR_TOP, AA_COLUMN_WIDTH, BAR_HEIGHT), 'TUI_InvFill',
              GOLD_RGB, track='TUI_InvTrack'),
        label('TUI_AAW_PercentLabel', None, (x, AA_SPLIT_TOP, AA_COLUMN_WIDTH, TEXT_HEIGHT), 'XP to AA',
              screen_id='PercentLabel'),
        icon_button('TUI_AAW_LessExpButton', 'LessExpButton', x, AA_SPLIT_ROW_TOP, None, 'Minus', ARROW_SIZE),
        static_text('TUI_AAW_ExpCount', 'ExpCount',
                    (x + ARROW_SIZE + PADDING, AA_SPLIT_ROW_TOP + SOCIAL_PAGE_LABEL_TOP,
                     AA_COLUMN_WIDTH - 2 * (ARROW_SIZE + PADDING), TEXT_HEIGHT), align_center=True, rgb=VALUE_RGB),
        icon_button('TUI_AAW_MoreExpButton', 'MoreExpButton', right - ARROW_SIZE, AA_SPLIT_ROW_TOP, None, 'Plus',
                    ARROW_SIZE),
    ]
    # The counts are StaticText, the timer a label, as in the stock window.
    value_x = right - AA_VALUE_WIDTH
    for n, (caption_id, caption, value_id) in enumerate(AA_NUMBERS):
        top = AA_NUMBERS_TOP + n * TEXT_HEIGHT
        rect = (value_x, top, AA_VALUE_WIDTH, TEXT_HEIGHT)
        parts += [
            label(f'TUI_AAW_{caption}', None, (x, top, value_x - x, TEXT_HEIGHT), caption, screen_id=caption_id),
            label(f'TUI_AAW_{value_id}', None, rect, '', align_right=True, screen_id=value_id, rgb=VALUE_RGB)
            if value_id == 'Timer' else
            static_text(f'TUI_AAW_{value_id}', value_id, rect, align_right=True, rgb=VALUE_RGB),
        ]
    parts += [button(f'TUI_AAW_{screen_id}', screen_id, '', x, AA_BUTTONS_TOP + n * (TEXT_BUTTON_HEIGHT + BUTTON_ROW_GAP),
                     AA_COLUMN_WIDTH, TEXT_BUTTON_HEIGHT, font=ACTION_FONT, text=button_name)
              for n, (screen_id, button_name) in enumerate(AA_BUTTONS)]
    return window('AAWindow', 'Alternate Advancement Window', AA_HEIGHT, parts, width=AA_WIDTH,
                  inner=[*inner, percent])


def friends_window():
    """Your friends and the players you ignore, each on a tab over its list, a divider under the tabs, and under each
    list the name field and Add, then Delete, and on the friends' tab Contact and Who (see FRIENDS_FILE). Positions on a
    page are from its top left, which the tab box puts under the divider and a padding in from the window's left (see
    LIST_PAGE_BORDER)."""
    inner = []
    for screen_id, name, list_id, field_id, add_id, delete_id, more in FRIENDS_PAGES:
        names = listbox(f'TUI_FW_{list_id}', list_id, (0, 0, FRIENDS_CONTENT_WIDTH, FRIENDS_LIST_HEIGHT), None,
                        FRIENDS_COLUMNS)
        # The field looks like the quantity window's: the strip, and the see-through name box on it, inset
        # FIELD_PADDING each side. The strip is a picture of the field template's look, not the quantity window's
        # child Screen: the game can't load a skin whose Page lists a Screen (UIErrors.txt: Couldn't find
        # class:item ... reference in FieldParseItemOfClass()), though a window's Screen can list one.
        strip = picture(f'TUI_FW_{field_id}Field', 'TUI_FriendsField',
                        (0, FRIENDS_FIELD_TOP, FRIENDS_FIELD_WIDTH, INPUT_HEIGHT))
        field = node('Editbox', [
            node('ScreenID', field_id),
            node('Font', TEXT_FONT),
            node('DrawTemplate', EDIT_TEMPLATE),
            node('RelativePosition', True),
            point('Location', FIELD_PADDING, FRIENDS_FIELD_TOP),
            size(FRIENDS_FIELD_WIDTH - 2 * FIELD_PADDING, INPUT_HEIGHT),
            node('Style_Border', False),
            node('Style_Transparent', True),
            color('TextColor', TEXT_RGB),
        ], f'TUI_FW_{field_id}')
        add = button(f'TUI_FW_{add_id}', add_id, '', FRIENDS_LEFTS[-1], FRIENDS_FIELD_TOP, FRIENDS_THIRDS[-1],
                     TEXT_BUTTON_HEIGHT, font=ACTION_FONT, text='Add')
        buttons = [button(f'TUI_FW_{button_id}', button_id, '', FRIENDS_LEFTS[column], FRIENDS_BUTTONS_TOP,
                          FRIENDS_THIRDS[column], TEXT_BUTTON_HEIGHT, font=ACTION_FONT, text=button_name)
                   for column, (button_id, button_name) in enumerate(((delete_id, 'Delete'), *more))]
        parts = [names, strip, field, add, *buttons]
        inner += parts + [page(f'TUI_FW_{screen_id}', screen_id, None, name, parts)]
    tabs = node('TabBox', [
        node('ScreenID', 'Subwindows'),
        node('Font', TEXT_FONT),  # its height + 8 is the least tab row, which our tabs are taller than
        node('RelativePosition', True),
        point('Location', 0, 0),
        size(TAB_BOX_WIDTH, FRIENDS_HEIGHT - 2 * BORDER),  # TAB_OVERHANG past the inside, as the Actions window's
        node('TabBorderTemplate', TAB_BORDER),
        node('PageBorderTemplate', LIST_PAGE_BORDER),
    ] + [node('Pages', f'TUI_FW_{screen_id}') for screen_id, *_ in FRIENDS_PAGES], 'TUI_FW_Tabs')
    # The divider under the tabs: the Actions window's, the same width.
    divider = picture('TUI_FW_TabDivider', 'TUI_ActionsDivider',
                      (LEFT, TAB_DIVIDER_TOP, FRIENDS_CONTENT_WIDTH, DIVIDER_HEIGHT))
    return window('FriendsWindow', 'Friends Window', FRIENDS_HEIGHT, [tabs, divider], width=FRIENDS_WIDTH,
                  inner=inner)


WINDOW_FILES = {GROUP_FILE: group_window, TARGET_FILE: target_window, CASTING_FILE: casting_window,
                CHAT_FILE: chat_window, PET_WINDOW_FILE: pet_window, SELECTOR_FILE: selector_window,
                BUFF_FILE: buff_window, SONG_FILE: song_window, PLAYER_FILE: player_window,
                ACTIONS_FILE: actions_window, CASTSPELL_FILE: spell_bar_window, HOTBUTTON_FILE: hot_button_window,
                BREATH_FILE: breath_window, RAID_FILE: raid_window, CONTAINER_FILE: container_window,
                MERCHANT_FILE: merchant_window, CONFIRM_FILE: confirmation_dialog, ITEM_FILE: item_display_window,
                QUANTITY_FILE: quantity_window, GIVE_FILE: give_window, TRADE_FILE: trade_window,
                LOOT_FILE: loot_window, COMPASS_FILE: compass_window, BANK_FILE: bank_window,
                SKILLS_FILE: skills_window, SPELLBOOK_FILE: spellbook_window, INVENTORY_FILE: inventory_window,
                TRACKING_FILE: tracking_window, AA_FILE: aa_window, FRIENDS_FILE: friends_window}


def stranded_definitions(skin_xml):
    """The definitions in the skin's own copies of the window files we replace that its other files still
    use, as text: duxaUI's player window defines the animation Blackbox, which its hot button window
    uses, and the client couldn't load it once our player window replaced theirs.

    skin_xml maps each XML file the client would load (the base's, else default's) to its text.
    """
    replaced = {name.lower() for name in WINDOW_FILES}
    kept = [text for name, text in skin_xml.items() if name.lower() not in replaced]
    stranded = []
    for name, text in skin_xml.items():
        if name.lower() not in replaced:
            continue
        for match in re.finditer(r'<(\w+)\s+item\s*=\s*"([^"]+)"\s*>.*?</\1\s*>', text, flags=re.S):
            tag, item = match.groups()
            used = re.compile(rf'>\s*{re.escape(item)}\s*<')
            if tag != 'Screen' and any(used.search(other) for other in kept):
                stranded.append(match.group(0))
    return stranded


def skin_files(base_animations, stranded=()):
    """Every file TriageUI adds to the base skin, as name → bytes.

    base_animations is the text of the base skin's EQUI_Animations.xml, which gets our shared definitions,
    and the stranded definitions (see stranded_definitions) so the base's other windows still find them.
    """
    atlas, rects = build_atlas(pieces())
    textures = {
        PIECES_TEXTURE: atlas,
        BACKGROUND_TEXTURE: Texture(BACKGROUND_SIZE, BACKGROUND_SIZE, PANEL_RGBA),
        PERCENT_TEXTURE: percent_glyph(),
        FIELD_TEXTURE: Texture(BACKGROUND_SIZE, BACKGROUND_SIZE, FIELD_RGBA),
        GUTTER_TEXTURE: clear_texture(BACKGROUND_SIZE, BACKGROUND_SIZE),
        DIVIDER_TEXTURE: Texture(BACKGROUND_SIZE, BACKGROUND_SIZE, ROW_DIVIDER_RGBA),
    }
    # Every pixel on the 16 steps, so the client has nothing to dither (see STEP).
    files = {name: tga_bytes(snapped_art(texture)) for name, texture in textures.items()}
    files[ANIMATIONS_FILE] = with_definitions(base_animations, shared_definitions(rects), stranded).encode('latin-1')
    for name, make in WINDOW_FILES.items():
        files[name] = xml_document(make()).encode('ascii')
    return files


def find_file(folder, name):
    """folder's file called name in any letter case, as Windows matches names, or None."""
    if folder.is_dir():
        for path in folder.iterdir():
            if path.is_file() and path.name.lower() == name.lower():
                return path
    return None


def build(eq_dir, base=DEFAULT_BASE, out=None):
    """Builds the skin into out (uifiles/TriageUI by default): TriageUI's files, over a copy of the base skin's
    unless the base is default, which the client falls back to anyway."""
    uifiles = Path(eq_dir) / 'uifiles'
    base_dir = uifiles / base
    on_default = base.lower() == DEFAULT_BASE.lower()
    out = Path(out) if out else uifiles / SKIN_NAME
    if not base_dir.is_dir():
        raise BuildError(f'There is no skin folder {base_dir}')
    if out.resolve() == base_dir.resolve():
        raise BuildError('The output folder must not be the base skin')
    if out.exists() and not (out / MARKER_FILE).is_file():
        raise BuildError(f'{out} already exists and wasn\'t built by this script, so it was left alone')
    # A skin without its own animations uses default's, so ours extend whichever the client would load.
    animations = find_file(base_dir, ANIMATIONS_FILE) or find_file(uifiles / 'default', ANIMATIONS_FILE)
    if not animations:
        raise BuildError(f'{base} has no {ANIMATIONS_FILE}' if on_default else
                         f'Neither {base} nor default has {ANIMATIONS_FILE}')
    # Every XML file the client would load with this skin: the base's, else default's, by name in any case.
    skin_xml = {}
    for folder in (uifiles / 'default', base_dir):
        if folder.is_dir():
            for path in folder.glob('*'):
                if path.is_file() and path.suffix.lower() == '.xml':
                    skin_xml = {name: text for name, text in skin_xml.items() if name.lower() != path.name.lower()}
                    skin_xml[path.name] = path.read_bytes().decode('latin-1')
    # Bytes, not text mode, so the file's own line endings survive.
    files = skin_files(animations.read_bytes().decode('latin-1'), stranded_definitions(skin_xml))
    try:
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        ours = {name.lower() for name in files}
        # Only the top level: the client never reads subfolders, which hold a skin's optional extras.
        for source in [] if on_default else base_dir.iterdir():
            if source.is_file() and source.name.lower() not in ours:
                shutil.copy2(source, out / source.name)
        for name, data in files.items():
            (out / name).write_bytes(data)
        (out / MARKER_FILE).write_text(
            f'Built by TriageUI {VERSION}\'s build_skin.py from uifiles\\{base}. Rebuild rather than edit: '
            f'the script replaces this folder.\n{LICENSE_NOTICE}\n'
        )
    except OSError as error:
        raise BuildError(f'Couldn\'t write {out}: {error}') from error
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description='Builds the TriageUI skin into your EverQuest uifiles folder.')
    parser.add_argument('--eq', type=Path, default=DEFAULT_EQ_DIR,
                        help=f'your EverQuest folder (default {DEFAULT_EQ_DIR})')
    parser.add_argument('--base', default=DEFAULT_BASE,
                        help=f'the skin in uifiles to start from (default {DEFAULT_BASE})')
    parser.add_argument('--out', type=Path, help=f'where to build (default uifiles\\{SKIN_NAME})')
    args = parser.parse_args(argv)
    try:
        out = build(args.eq, args.base, args.out)
    except BuildError as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    print(f'Built TriageUI {VERSION} into {out} from {args.base}.')
    # The 1 keeps the character's window layout; without it windows move to the skin's default spots.
    print(f'In game, type /load {out.name} 1 to use it, and /load <skin> 1 to go back to another.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
