"""TriageUI: EverQuest windows for Project Quarm in the look of EQ Triage's overlays.

The script writes a skin folder of TriageUI's own windows and art. For everything else the game falls
back to its own UI files (uifiles/default), so every window TriageUI hasn't redesigned keeps EverQuest's
own look; --base builds it on another skin of yours instead. It uses only the standard library, and it
never changes the skin it reads.

Copyright 2026 Sebik <Europa>, licensed under CC BY-NC-SA 4.0: see LICENSE.
"""

import argparse
import functools
import math
import random
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
# The spell book's page strips and its pages, too big for the atlas (see BOOK_TURN_WIDTH and book_spread()).
BOOK_TEXTURE = 'triageui_book.tga'
BOOK_TEXTURE_WIDTH = 1024
BOOK_TEXTURE_HEIGHT = 512
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
# user's call). The client stretches them to each slot, so the spell book's and item window's slots are shaped so
# the red bars fall under their icons (see BOOK_SLOT_MARGIN).
BUFF_FILE = 'EQUI_BuffWindow.xml'
SONG_FILE = 'EQUI_ShortDurationBuffWindow.xml'
# The stock slots' decal: a placeholder the client replaces with the spell's A_SpellIcons cell, scaled to the decal.
BUFF_ICONS = 'BuffIcons'
# Art the client paints by name that the skin redefines: the effect slots' backgrounds, the spellbook's empty slot, and
# every spell's icon at both sizes (see SPELL_ICON_SHEETS).
REPLACED_ANIMATIONS = ('BlueIconBackground', 'RedIconBackground', 'A_SpellBookSlot', 'A_SpellIcons', 'A_SpellGems')
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
# label hook could). The client stretches the art to the slot, which is the art's own size here, so clear pixels
# put the bars in place. Before them: a faint red across the row, then a red square behind the icon at alpha 85, which
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
# The client draws a gem's icon from A_SpellGems (24px cells), which the client names itself: ours (see
# SPELL_ICON_SHEETS). It draws the gem's Holder and Background under the icon
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
# RedIconBackground, the effect slots' art, stretched to the button, which is the icon's size, so the red bars fall
# under the icon (see BOOK_SLOT_MARGIN). Neither moves nor resizes anything. The window handles one click, on the
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
# The spell book: two parchment pages side by side in the window's dark panel, its cover, each two spells across by four
# down in the stock book's reading order, a spell's icon at the icons' own 40px in a thin frame with its name in ink
# centered under it (the user's picks, 2026-09-30, from mockups: the layout over eight rows a page like the spell
# bar's, then the parchment over the same layout in the overlay's look, so the book is the one window that leaves it). A
# thin bar along the top for memorizing or scribing, like the spell bar's recovery bar; Previous and Next as tall
# strips down the window's sides; the page numbers and Done along the bottom. eqgame.exe looks up
# SBW_Spell%d and SBW_SpellName%d (16 of each), SBW_PageDown_Button and SBW_PageUp_Button, SBW_MemPage0_Button and
# SBW_MemPage1_Button (no size in every skin), SBW_LeftPageNum and SBW_RightPageNum, and DoneButton; the bars by
# EQType, 9 memorizing and 10 scribing, which never run together, so they share a spot (as in duxaUI). The stock
# book art (SBW_SpellBook1 to 4) is nothing the client looks up, so it's left out. The names and page numbers are
# StaticText, which takes no click (see static_text()).
SPELLBOOK_FILE = 'EQUI_SpellBookWnd.xml'
BOOK_SPELLS = 16
BOOK_COLUMNS = 2  # a page's spells across
BOOK_PAGE_ROWS = 4
BOOK_PAGE_SPELLS = BOOK_COLUMNS * BOOK_PAGE_ROWS
BOOK_ICON = 40  # A_SpellIcons' cells, drawn at their own size
# The client paints a detrimental spell's slot RedIconBackground, the Effects window's art, stretched to the slot's
# size: its bars stood over the names on rows (seen in game 2026-09-29), then down most of a 100 by 92 tile left of its
# icon (2026-09-30). So each slot is the stock book's, the icon this far in all round: stretched to 44px, the bars (see
# HARMFUL_BARS) cover x 6 to 10.8 and y 4.4 to 39.6, inside the icon by more than a pixel of filtering, and clear of its
# bottom row, which six cells of spells01 leave see-through. A bigger slot lets red out (48 with the icon at 4 puts it
# on the row above the icon and on that bottom row), so only the icon and the ring round it take a click, and the name
# under it takes none. Panel-colored patches over the bars would show at any Alpha under 255.
BOOK_SLOT_MARGIN = 2
BOOK_SLOT = BOOK_ICON + 2 * BOOK_SLOT_MARGIN
# Each spell's frame, a line on the page just outside its slot, so an empty spot shows where a spell goes.
BOOK_FRAME_LINE = 1
BOOK_FRAME = BOOK_SLOT + 2 * BOOK_FRAME_LINE
# A spell's tile: its name a padding in from each side, centered and wrapping onto as many as 3 lines, with its frame
# centered over it. At 88px in font 3 (Arial 12px), 739 of the 1789 names a class can scribe (spells_en.txt) take 2
# lines and 74 take 3. Only two single words run wider, VampEmbraceNecro and VampEmbraceShadow.
BOOK_NAME_WIDTH = 88
BOOK_NAME_LINES = 3
BOOK_TILE_WIDTH = BOOK_NAME_WIDTH + 2 * PADDING
BOOK_FRAME_X = (BOOK_TILE_WIDTH - BOOK_FRAME) // 2  # in its tile
BOOK_PAGE_WIDTH = BOOK_COLUMNS * BOOK_TILE_WIDTH
# Down a page: each frame a padding under the page's top edge or the row above's letters, the name's ink a padding
# under the frame, and a three-line name's letters, which end where the digits do, a padding over the next frame or
# the page's bottom edge. So a row, frame to frame:
BOOK_NAME_TOP = BOOK_FRAME + math.ceil(PADDING - TEXT_INK_TOP)  # from the frame's top
BOOK_INK_BOTTOM = TEXT_INK_TOP + PERCENT_GLYPH_HEIGHT - math.ceil(PERCENT_SUBPIXEL)  # from a line's top
BOOK_ROW_HEIGHT = math.ceil(BOOK_NAME_TOP + (BOOK_NAME_LINES - 1) * TEXT_HEIGHT + BOOK_INK_BOTTOM + PADDING)
# Previous and Next: strips as tall as the window's inside and as wide as the stock book's arrows, down its sides,
# where they never move, so a page can be turned again and again without looking, a padding clear of the pages, where
# a click takes no spell. Their art is too tall for the atlas (see BOOK_TEXTURE).
BOOK_TURN_WIDTH = 30
BOOK_ARROWS = (('SBW_PageDown_Button', 'Previous Page', 'Left'), ('SBW_PageUp_Button', 'Next Page', 'Right'))
BOOK_LEFT = LEFT + BOOK_TURN_WIDTH + PADDING
# The spine between the pages: a crease a padding from each.
BOOK_CREASE_X = BOOK_LEFT + BOOK_PAGE_WIDTH + PADDING
BOOK_PAGE_XS = (BOOK_LEFT, BOOK_CREASE_X + DIVIDER_HEIGHT + PADDING)  # each page's left
BOOK_RIGHT = BOOK_PAGE_XS[1] + BOOK_PAGE_WIDTH
BOOK_CONTENT_WIDTH = BOOK_RIGHT - BOOK_LEFT  # both pages, which the bar spans
BOOK_TURN_XS = (LEFT, BOOK_RIGHT + PADDING)
SPELLBOOK_WIDTH = BOOK_TURN_XS[1] + BOOK_TURN_WIDTH + LEFT + 2 * BORDER
MEMORIZE_TYPE = 9
SCRIBE_TYPE = 10
BOOK_BAR_TOP = LEFT
# The pages a padding under the bar, a padding over their first frames, and the band a padding under them.
BOOK_PAGES_TOP = BOOK_BAR_TOP + TICK_HEIGHT + PADDING
BOOK_PAGES_HEIGHT = PADDING + BOOK_PAGE_ROWS * BOOK_ROW_HEIGHT
BOOK_BAND_TOP = BOOK_PAGES_TOP + BOOK_PAGES_HEIGHT + PADDING
# Done the loot and bank windows', centered on the crease.
BOOK_DONE_WIDTH = COIN_WIDTH
add_text_buttons((BOOK_DONE_WIDTH,))
BOOK_TURN_HEIGHT = BOOK_BAND_TOP + TEXT_BUTTON_HEIGHT - BOOK_BAR_TOP
SPELLBOOK_HEIGHT = 2 * BORDER + BOOK_BAND_TOP + TEXT_BUTTON_HEIGHT + BOTTOM_GAP
# The pages' look, the book's own: parchment a shade under the cream behind the stock spell icons, so they stand out,
# a darker edge round it, a grain of single pixels a step darker or lighter, and shading from BOOK_SHADE_WIDTH out of
# the crease down to BOOK_SPINE_RGB beside it, with the crease a line of its own. The frames a mid brown and the names
# dark brown ink, as dark as the stock book's black names on its parchment; the ring round an icon gold under the
# pointer (see book_slot_art()), darker while pressed. Greens are on the 16 steps (see STEP), and the shading's
# in-between greens are scattered between the steps either side, like the grain, so it never shows bands.
PARCHMENT_RGB = (224, 204, 160)
BOOK_PAGE_EDGE_RGB = (150, 119, 80)
BOOK_SPINE_RGB = (170, 136, 96)
BOOK_CREASE_RGB = (120, 85, 51)
BOOK_SHADE_WIDTH = 18
BOOK_GRAIN = (0.07, 0.03)  # the share of pixels a step darker, and a step lighter
BOOK_GRAIN_SEED = 1  # the same grain every build
BOOK_FRAME_RGB = (120, 85, 51)
BOOK_INK_RGB = (58, 40, 24)
BOOK_RING_RGB = {'Flyby': (221, 170, 51), 'Pressed': (187, 136, 34)}
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
# The inspect window: another player's worn gear and the message they wrote for it. eqgame.exe looks up the message
# (INSW_Edit), the worn slots (InvSlot%d, EQTypes 8001 to 8021: the inventory's, INSPECT_SLOT_TYPE on) and DoneButton,
# and writes the player's name on the title bar. Zeal finds InvSlot1 to 21 by name to link an item Alt+clicked
# (ui_inspect.cpp). The user's picks (2026-09-30, from mockups): the worn slots where the inventory window has them, the
# message in their middle and Done along the bottom; a title bar with the name alone, since the game centers it across
# the bar and in a window this narrow a longer name would run under the item window's Close.
INSPECT_FILE = 'EQUI_InspectWnd.xml'
INSPECT_TEMPLATE = 'WDT_TriageInspect'
INSPECT_SLOT_TYPE = 8000
# The game writes the name (bar height - TEXT_HEIGHT) // 2 - 1 down the bar (0x5729b0). The least height that puts the
# divider, the bar's bottom row, a padding under the name's baseline; that leaves its ink about 10.5px under the window's
# edge, where the game puts it.
INSPECT_TITLE_HEIGHT = 23
INSPECT_DOLL_TOP = PADDING  # under the bar's divider, where the controls' inside starts
INSPECT_WIDTH = INV_DOLL_WIDTH + 2 * LEFT + 2 * BORDER
# The message on the chat input's strip over the inventory's middle, a padding from every slot around it. The box is
# inset FIELD_PADDING at the sides and the bottom, and its first line's ink about as far under the strip's top, if the
# box draws its first line at its top like a label.
INSPECT_FIELD_X = LEFT + HOT_PITCH
INSPECT_FIELD_TOP = INSPECT_DOLL_TOP + HOT_PITCH
INSPECT_TEXT_TOP = math.ceil(FIELD_PADDING - TEXT_INK_TOP)
# Done a padding under the worn slots, across them: the confirmation dialog's button, with no tooltip (the stock one
# has none).
INSPECT_BUTTON_TOP = INSPECT_DOLL_TOP + INV_DOLL_HEIGHT + BUTTON_ROW_GAP
add_text_buttons((INV_DOLL_WIDTH,))
INSPECT_HEIGHT = 2 * BORDER + INSPECT_TITLE_HEIGHT + INSPECT_BUTTON_TOP + TEXT_BUTTON_HEIGHT + BOTTOM_GAP
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
# under them, and a column on the right with your points, how much of your XP goes to AA and the ability's reuse
# timer, then Train, Hotkey and Done. eqgame.exe looks up the tab box (Subwindows), its pages and their lists
# (Page%d and List%d, 1 to 5), Description, ExpCount, CurrentCount, TotalCount, Timer, LessExpButton, MoreExpButton,
# TrainButton, HotButton and DoneButton, and fills them all; nothing looks up the stock bar (ExpGauge, hidden: see
# AA_NUMBERS_TOP) or the stock captions, which keep their ScreenIDs as ours. The user's pick (2026-09-29, from mockups): the stock arrangement,
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
# The column's sections, in the user's order, each set apart by the row divider across the column like the inventory's
# stats (a padding under what's above, a padding over the next ink): your points spent and available, stacked on their
# line height, the first line at the inside's top like the inventory's stats (its ink 7.5px under the edge); how much of
# your XP goes to AA, a caption over the client's % between - and + (the social page arrows' size, the digits' ink
# centered on them); and the selected ability's reuse timer, the client's Timer, on the line under its caption. They
# asked for the points earned on top too, but the client gives only the unspent and spent counts, no label EQType has
# either, and a skin can't add them. No AA XP line: the inventory shows it (the user's pick), and the stock ExpGauge
# stays, hidden.
AA_NUMBERS_TOP = 0
# (caption's ScreenID, caption, value's ScreenID), each value in the game's green ending at the column's right: the
# stock captions' ScreenIDs, which nothing looks up.
AA_NUMBERS = (('TotalLabel', 'Spent', 'TotalCount'), ('CurrentLabel', 'Available', 'CurrentCount'))
AA_POINTS_DIVIDER_TOP = AA_NUMBERS_TOP + (len(AA_NUMBERS) - 1) * TEXT_HEIGHT + INV_DIGITS_BOTTOM + PADDING
AA_SPLIT_TOP = AA_POINTS_DIVIDER_TOP + DIVIDER_HEIGHT + DIVIDER_TO_NAME
AA_SPLIT_ROW_TOP = AA_SPLIT_TOP + PERCENT_INK_TOP + PERCENT_GLYPH_HEIGHT + PADDING
AA_SPLIT_DIVIDER_TOP = AA_SPLIT_ROW_TOP + ARROW_SIZE + PADDING
AA_TIMER_TOP = AA_SPLIT_DIVIDER_TOP + DIVIDER_HEIGHT + DIVIDER_TO_NAME  # the caption's; the timer's is a line under it
AA_TIMER_CAPTION = 'Ability ready in:'
# The dividers are the inventory's column's art, the column being as wide.
AA_COLUMN_DIVIDERS = (('TUI_AAW_PointsDivider', AA_POINTS_DIVIDER_TOP), ('TUI_AAW_SplitDivider', AA_SPLIT_DIVIDER_TOP))
AA_VALUE_WIDTH = 28  # "0000" in font 3 (Arial 12px), more than any count reaches
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


# The spell icons: the client draws every spell's picture from A_SpellIcons (40px cells: the spell book, the item
# window and the Effects rows, scaled to 16) and A_SpellGems (24px: the spell bar, spell hot buttons, the cursor),
# the same picture at two sizes by the same cell number (spells_en.txt's field 131). Both are redefined here, over
# our own sheets laid out like the stock ones, so no skin's pictures show. Each picture keeps the idea of duxaUI's
# (its subject, colors and where its second object sits) and is painted: objects in their own colors, outlined,
# shaded and glowing, on a rounded tile in the spell's color that glows from its middle. Light line pictures on a
# flat tile, like the selector's icons, were tried first and read as too plain. A cell with no picture yet is its
# tile alone.
SPELL_ICON_SHEETS = tuple(f'triageui_spells{n:02}.tga' for n in range(1, 6))  # A_SpellIcons: BOOK_ICON cells
GEM_ICON_SHEETS = tuple(f'triageui_gems{n:02}.tga' for n in range(1, 3))  # A_SpellGems: GEM_ICON cells
ICON_SHEET = 256  # each sheet's side, as the stock ones: 6 by 6 cells of 40px, 10 by 10 of 24px
SPELL_ICON_CELLS = len(SPELL_ICON_SHEETS) * (ICON_SHEET // BOOK_ICON) ** 2  # 180
GEM_ICON_CELLS = len(GEM_ICON_SHEETS) * (ICON_SHEET // GEM_ICON) ** 2  # 200
# A picture is drawn on the selector icons' 16-unit grid (ICON_SIZE), scaled to the cell less this margin each side.
SPELL_ICON_MARGIN = {BOOK_ICON: 4, GEM_ICON: 2}
# Each tile: (dark at the corners, bright at the middle, its 1px edge), by the spell's kind as duxaUI colors it: blue
# heals and buffs, sky pale buffs, purple the enchanter's and the mind's, pink charm and sense, red harm and plain
# damage, crimson death and fear, orange fire, gold holy and wealth, green nature, poison and travel, olive disease,
# teal water and mana, ice cold, grey sight and stealth, brown earth and lore.
SPELL_TILES = {
    'blue': ((12, 30, 86), (54, 104, 204), (120, 165, 235)),
    'sky': ((20, 44, 90), (90, 150, 220), (150, 205, 240)),
    'purple': ((38, 8, 60), (124, 42, 168), (178, 122, 236)),
    'pink': ((56, 12, 44), (150, 50, 120), (228, 125, 195)),
    'red': ((58, 10, 16), (150, 36, 44), (236, 110, 110)),
    'crimson': ((36, 4, 10), (110, 16, 32), (190, 55, 85)),
    'orange': ((34, 12, 6), (104, 40, 12), (236, 140, 64)),
    'gold': ((44, 32, 6), (140, 110, 30), (228, 190, 90)),
    'green': ((8, 36, 22), (30, 96, 60), (100, 196, 112)),
    'olive': ((22, 30, 10), (86, 100, 40), (170, 180, 84)),
    'teal': ((4, 36, 40), (24, 110, 120), (64, 186, 186)),
    'ice': ((18, 14, 62), (64, 56, 160), (128, 216, 232)),
    'grey': ((32, 34, 40), (108, 112, 122), (172, 178, 192)),
    'brown': ((40, 24, 12), (116, 76, 44), (178, 130, 88)),
}
# Every cell's tile, following duxaUI's background (a black one takes its element's dark: fire's ember, cold's
# indigo). Cells 166 to 199 are in no Quarm spell (spells_en.txt's field 131 runs 0 to 165), so they're all the plain
# grey tile, with no picture (the user's call).
SPELL_TILE_CELLS = {
    'blue': (0, 2, 10, 13, 16, 21, 22, 24, 30, 49, 77, 78, 80, 97, 98, 99, 103, 104, 106, 116, 132, 141, 146, 150, 151,
             156, 163),
    'sky': (26, 118, 119, 133, 134),
    'purple': (1, 6, 8, 9, 11, 15, 35, 37, 38, 40, 69, 71, 72, 87, 96, 109, 121, 129, 144, 162),
    'pink': (36, 70, 75, 82, 86, 124),
    'red': (3, 7, 12, 14, 17, 25, 29, 32, 50, 53, 85, 105, 107, 114, 143, 153, 161, 164, 165),
    'crimson': (27, 28, 47, 91, 95, 110, 113, 122, 135, 136, 139, 140, 145, 154, 158),
    'orange': (51, 52, 54, 55, 89, 147, 157),
    'gold': (23, 46, 73, 83, 90, 101, 130, 138),
    'green': (4, 5, 31, 42, 45, 61, 62, 63, 64, 67, 74, 76, 81, 93, 94, 112, 117, 120, 123, 127, 131, 155),
    'olive': (41, 65, 66, 68, 149, 160),
    'teal': (20, 111, 115, 128, 152),
    'ice': (56, 57, 58, 59, 60),
    'grey': (18, 19, 33, 34, 44, 48, 92, 100, 108, 137, 142, 148, *range(166, 200)),
    'brown': (39, 43, 79, 84, 88, 102, 125, 126, 159),
}
SPELL_TILE = {cell: tile for tile, cells in SPELL_TILE_CELLS.items() for cell in cells}
# The objects' own colors, shared so a hand or a skull looks the same on every icon: (light, mid, rim).
SKIN_TONES = ((240, 222, 212), (206, 170, 158), (120, 84, 78))
BONE = ((246, 238, 214), (196, 180, 140), (110, 92, 60))
STEEL = ((246, 248, 252), (160, 168, 184), (70, 76, 92))
GOLD = ((255, 226, 130), (214, 160, 50), (120, 80, 20))
LEATHER = ((190, 128, 72), (120, 72, 36), (64, 36, 16))
FEATHER = ((255, 255, 255), (206, 214, 228), (120, 130, 150))
PICTURE_OUTLINE = (20, 14, 18, 230)  # the dark line round an object, parting it from the tile and what's behind


# A picture is a list of layers painted over its tile in order, each on the 16-unit grid: fill() paints a shape,
# glow() a shape and a halo fading out round it, outline() a dark line just outside a shape. A paint gives a color at
# a point of the grid and the shape's distance there (negative inside).

def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def mix(a, b, t):
    t = clamp(t)
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def opaque(color):
    return color if len(color) == 4 else (*color, 255)


def along(stops, t):
    """The color at t (0 to 1) through stops, [(t, color)]."""
    t = clamp(t)
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            return mix(opaque(c0), opaque(c1), (t - t0) / (t1 - t0 or 1))
    return opaque(stops[-1][1])


def flat(color):
    color = opaque(color)
    return lambda u, v, d: color


def linear(start, end, stops):
    """A gradient from start to end."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length2 = dx * dx + dy * dy
    return lambda u, v, d: along(stops, ((u - start[0]) * dx + (v - start[1]) * dy) / length2)


def radial(center, radius, stops):
    return lambda u, v, d: along(stops, math.hypot(u - center[0], v - center[1]) / radius)


def bevel(paint, rim, width=1.0, strength=0.5):
    """paint darkened toward its shape's edge, width deep, so the shape looks rounded."""
    def shaded(u, v, d):
        color = paint(u, v, d)
        return (*mix(color[:3], rim, strength * (1 - clamp(-d / width))), color[3])
    return shaded


_REMEMBERED = {}


def remembered(shape):
    """shape, keeping the distance at the last point asked: a picture's layers ask for the same shape at each pixel
    several times (its glow, its outline, its fill, parts inside it), which took most of the drawing's time. One
    stand-in per shape, so they all share it; spell_icon_art() clears them after each icon."""
    if shape not in _REMEMBERED:
        last = [None, None, 0.0]

        def distance(u, v):
            if u != last[0] or v != last[1]:
                last[0], last[1], last[2] = u, v, shape(u, v)
            return last[2]
        _REMEMBERED[shape] = distance
    return _REMEMBERED[shape]


def fill(shape, paint):
    return ('fill', remembered(shape), paint, None)


def glow(shape, paint, radius):
    """shape and a halo round it, fading to nothing radius out."""
    return ('glow', remembered(shape), paint, radius)


def outline(shape, color=PICTURE_OUTLINE, width=0.6):
    shape = remembered(shape)
    return ('fill', lambda u, v: abs(shape(u, v) - width / 2) - width / 2, flat(color), None)


def shaded(shape, palette, light=(3, 2), dark=(13, 14), width=1.0, strength=0.5):
    """shape in one of the object palettes, lit from light, bevelled to its rim."""
    lit, mid, rim = palette
    return fill(shape, bevel(linear(light, dark, [(0, lit), (1, mid)]), rim, width, strength))


def inside(shape, part):
    """part, only where it lies within shape."""
    shape = remembered(shape)
    return lambda u, v: max(part(u, v), shape(u, v))


def circle(x, y, cx, cy, r):
    return math.hypot(x - cx, y - cy) - r


def capsule(x, y, start, end, r):
    return segment_distance(x, y, start, end) - r


def tapered(x, y, start, end, r_start, r_end):
    """A capsule narrowing from r_start at start to r_end at end: a finger, a feather, a root."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    t = clamp(((x - start[0]) * dx + (y - start[1]) * dy) / (dx * dx + dy * dy))
    return math.hypot(x - start[0] - t * dx, y - start[1] - t * dy) - (r_start + (r_end - r_start) * t)


def curve(start, bend, end, r_start, r_end, steps=10):
    """A curve from start, pulled toward bend, to end, narrowing from r_start to r_end: a quadratic Bezier as steps
    tapered pieces. A root coiling round something."""
    points = [((1 - t) ** 2 * start[0] + 2 * (1 - t) * t * bend[0] + t * t * end[0],
               (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * bend[1] + t * t * end[1]) for t in (k / steps for k in range(steps + 1))]
    radii = [r_start + (r_end - r_start) * k / steps for k in range(steps + 1)]
    pieces = list(zip(points, points[1:], radii, radii[1:]))
    return lambda x, y: min(tapered(x, y, a, b, ra, rb) for a, b, ra, rb in pieces)


def tilted_ellipse(x, y, cx, cy, rx, ry, degrees):
    a = math.radians(degrees)
    u = (x - cx) * math.cos(a) + (y - cy) * math.sin(a)
    v = -(x - cx) * math.sin(a) + (y - cy) * math.cos(a)
    return ellipse_signed(u, v, 0, 0, rx, ry)


def placed(shape, cx, cy, scale):
    """shape, drawn on its own grid round (0, 0), put at (cx, cy) at scale."""
    return lambda u, v: shape((u - cx) / scale, (v - cy) / scale) * scale


# The objects the pictures share.

def open_hand(u, v):
    # An open hand, palm out: a palm narrowing to the wrist, four slim fingers fanned a little and tapering to their
    # tips, the thumb angled out low on the left. Fingers cut apart by gaps read as a glove; they meet in creases.
    palm = polygon_signed(u, v, [(4.3, 8.4), (12.1, 8.2), (11.8, 12.6), (10.4, 15.2), (5.9, 15.2), (4.6, 12.4)]) - 0.6
    fingers = min(tapered(u, v, (base, 8.8), tip, 1.0, 0.78)
                  for base, tip in ((5.3, (4.2, 3.9)), (7.3, (6.8, 1.5)), (9.3, (9.5, 1.7)), (11.2, (12.4, 4.2))))
    return min(palm, fingers, tapered(u, v, (5.4, 12.6), (1.9, 8.3), 1.25, 0.85))


def hand_creases(u, v):
    return min(segment_distance(u, v, (x, 9.6), (x + lean, 7.0)) for x, lean in ((6.3, -0.15), (8.3, 0.05), (10.25, 0.3))) - 0.22


def hand_layers(lit, mid, rim, halo=None):
    """The open hand in its colors: skin, or a spell's glowing color with a halo."""
    return [*([glow(open_hand, flat(halo), 3.0)] if halo else []),
            outline(open_hand),
            fill(open_hand, bevel(linear((4, 2), (12, 15), [(0, lit), (1, mid)]), rim, 1.2, 0.5)),
            fill(inside(open_hand, hand_creases), flat((*rim, 170)))]


def offered_hand(u, v):
    # A hand held out palm up, seen from the front: its curled fingers' row of tips along the bottom, the heel of the
    # palm behind them and the thumb rising on the left. From the side it read as a slab.
    palm = rounded_rect_distance(u, v, 2.4, 11.2, 13.8, 15.6, 2.2)
    tips = min(ellipse_signed(u, v, x, 12.2, 1.35, 1.55) for x in (4.6, 7.3, 10.0, 12.5))
    return min(palm, tips, tapered(u, v, (3.4, 13.4), (1.5, 9.6), 1.25, 0.9))


def offered_hand_layers():
    nails = lambda u, v: min(ellipse_signed(u, v, x, 11.6, 0.75, 0.62) for x in (4.6, 7.3, 10.0, 12.5))  # noqa: E731
    knuckles = lambda u, v: min(segment_distance(u, v, (x, 12.6), (x, 15.2)) for x in (5.95, 8.65, 11.25)) - 0.18  # noqa: E731
    lit, mid, rim = SKIN_TONES
    return [outline(offered_hand),
            fill(offered_hand, bevel(linear((3, 10), (13, 16), [(0, lit), (1, mid)]), rim, 1.1, 0.5)),
            fill(inside(offered_hand, knuckles), flat((*rim, 170))),
            fill(nails, flat((250, 226, 222)))]


def skull_layers(cx, cy, scale=1.0):
    """A bone skull about 6.5 across centered at (cx, cy): the cranium and jaw, dark eye sockets and nose, and teeth."""
    head = placed(lambda u, v: min(circle(u, v, 0, -0.7, 3.0), rounded_rect_distance(u, v, -1.85, 0.4, 1.85, 3.1, 0.7)),
                  cx, cy, scale)
    holes = placed(lambda u, v: min(circle(u, v, -1.18, -0.35, 0.86), circle(u, v, 1.18, -0.35, 0.86),
                                    polygon_signed(u, v, [(0, 0.55), (0.42, 1.45), (-0.42, 1.45)])), cx, cy, scale)
    teeth = placed(lambda u, v: min(segment_distance(u, v, (x, 2.1), (x, 3.2)) for x in (-0.62, 0, 0.62)) - 0.13,
                   cx, cy, scale)
    return [outline(head), shaded(head, BONE, (cx - 2, cy - 3), (cx + 2, cy + 3), 0.8, 0.45),
            fill(inside(head, holes), flat((40, 26, 18))), fill(inside(head, teeth), flat((90, 70, 44, 220)))]


def sparkle_layers(cx, cy, size, crossed=False, core=(255, 255, 255), rim=(255, 150, 200)):
    """A four-pointed star, turned 45 degrees when crossed, white at its heart, with a soft glow."""
    def star(u, v):
        x, y = u - cx, v - cy
        if crossed:
            x, y = (x + y) * math.sqrt(0.5), (y - x) * math.sqrt(0.5)
        return polygon_signed(x, y, four_point_star(0, 0, size, size * 0.22))
    return [glow(star, flat((*rim, 150)), 2.2), fill(star, radial((cx, cy), size, [(0, core), (1, rim)]))]


def sword_parts(base, tip, half=0.95, guard=2.4, grip=1.9):
    """A sword from its crossguard at base to its point at tip: the blade, its ridge, the guard, and the grip with its
    pommel, each a shape."""
    length = math.hypot(tip[0] - base[0], tip[1] - base[1])
    ux, uy = (tip[0] - base[0]) / length, (tip[1] - base[1]) / length

    def local(shape):
        return lambda u, v: shape((u - base[0]) * ux + (v - base[1]) * uy, -(u - base[0]) * uy + (v - base[1]) * ux)
    blade = local(lambda a, b: polygon_signed(a, b, [(0, -half), (length - 1.9, -half), (length, 0),
                                                     (length - 1.9, half), (0, half)]))
    ridge = local(lambda a, b: segment_distance(a, b, (0.3, 0), (length - 1.2, 0)) - 0.16)
    guard_bar = local(lambda a, b: capsule(a, b, (-0.5, -guard), (-0.5, guard), 0.55))
    grip_bar = local(lambda a, b: min(capsule(a, b, (-0.5, 0), (-grip, 0), 0.5), circle(a, b, -grip - 0.9, 0, 1.0)))
    return blade, ridge, guard_bar, grip_bar


def sword_layers(base, tip, halo=None, **size):
    """A steel sword with a gold guard and a leather grip, with a halo when it glows."""
    blade, ridge, guard_bar, grip_bar = sword_parts(base, tip, **size)
    whole = lambda u, v: min(blade(u, v), guard_bar(u, v), grip_bar(u, v))  # noqa: E731
    return [*([glow(whole, flat(halo), 3.0)] if halo else []), outline(whole, width=0.55),
            shaded(blade, STEEL, base, tip, 0.8, 0.45), fill(ridge, flat((255, 255, 255, 200))),
            shaded(grip_bar, LEATHER, base, tip, 0.6, 0.4),
            shaded(guard_bar, GOLD, (base[0] - 2, base[1] - 2), (base[0] + 2, base[1] + 2), 0.6, 0.4)]


def almond(u, v):
    # An eye's outline: two arcs meeting in corners 1.2 in from the grid's sides, 9.6 tall.
    return max(circle(u, v, 8, 11.02, 7.82), circle(u, v, 8, 4.98, 7.82))


def burst(u, v):
    return polygon_signed(u, v, four_point_star(8, 8, 7.6, 1.6))


def flame(u, v):
    # A flame with three tongues, the middle one tallest and leaning right.
    return min(circle(u, v, 8, 10.6, 4.3),
               polygon_signed(u, v, [(3.75, 10.2), (3.9, 4.4), (6.3, 7.0), (8.9, 0.8), (10.9, 6.4), (12.7, 4.8),
                                     (12.25, 10.2)]))


def snowflake(u, v):
    # Six thick arms, each with two V's of branches, round a hexagon.
    arms = []
    for k in range(6):
        a = math.radians(90 + 60 * k)
        ux, uy = math.cos(a), math.sin(a)
        arms.append(segment_distance(u, v, (8, 8), (8 + 6.9 * ux, 8 + 6.9 * uy)))
        for reach, spread in ((4.1, 2.5), (2.2, 1.6)):
            x, y = 8 + reach * ux, 8 + reach * uy
            for side in (-1, 1):
                b = a + side * math.radians(45)
                arms.append(segment_distance(u, v, (x, y), (x + spread * math.cos(b), y + spread * math.sin(b))))
    hexagon = [(8 + 1.9 * math.cos(math.radians(30 + 60 * k)), 8 + 1.9 * math.sin(math.radians(30 + 60 * k)))
               for k in range(6)]
    return min(min(arms) - 0.95, polygon_signed(u, v, hexagon))


def heater_shield(u, v):
    # A flat top and straight sides curving down to a point, a little right of the middle.
    right = [(13.6, 2.2), (13.6, 7.4), (13.0, 10.2), (11.1, 12.8)]
    return polygon_signed(u, v, [(9.2, 15.0)] + [(18.4 - x, y) for x, y in right[::-1]] + right) - 0.3


# The pictures, by cell: each gives its layers.

def strike_picture():
    # 161, the plain nuke: a white-hot four-pointed star over a turned smaller one, in a pink glow.
    back = lambda u, v: polygon_signed(8 + (u + v - 16) * math.sqrt(0.5), 8 + (v - u) * math.sqrt(0.5),  # noqa: E731
                                       four_point_star(8, 8, 5.0, 1.3))
    return [glow(burst, flat((255, 110, 120, 150)), 4.5),
            fill(back, radial((8, 8), 5, [(0, (255, 200, 205)), (1, (240, 110, 125))])),
            fill(burst, radial((8, 8), 7.6, [(0, (255, 255, 255)), (0.35, (255, 225, 228)), (1, (245, 120, 135))])),
            fill(lambda u, v: circle(u, v, 8, 8, 1.6), flat((255, 255, 255)))]


def fire_picture():
    # 51: a flame, red at its tips to yellow at its base, a white-yellow heart, in an orange glow.
    heart = lambda u, v: min(circle(u, v, 8, 11.5, 2.4),  # noqa: E731
                             polygon_signed(u, v, [(5.7, 11.0), (7.4, 7.6), (8.8, 4.8), (10.3, 11.0)]))
    return [glow(flame, flat((255, 120, 30, 140)), 3.0), outline(flame, (70, 18, 6, 230)),
            fill(flame, linear((8, 1), (8, 15), [(0, (214, 52, 26)), (0.45, (246, 128, 36)), (1, (255, 206, 80))])),
            fill(heart, linear((8, 5), (8, 14), [(0, (255, 214, 96)), (1, (255, 250, 214))]))]


def poison_picture():
    # 42: a skin-toned hand holding a vial of glowing green poison across it, the liquid at the bottom left.
    start, end = (3.0, 13.4), (13.0, 3.4)

    def at(t, off=0.0):
        return (start[0] + (end[0] - start[0]) * t + off, start[1] + (end[1] - start[1]) * t + off)
    glass = lambda u, v: capsule(u, v, at(0.06), at(0.80), 1.75)  # noqa: E731
    liquid = lambda u, v: capsule(u, v, at(0.06), at(0.52), 1.2)  # noqa: E731
    shine = lambda u, v: capsule(u, v, at(0.18, -0.75), at(0.62, -0.75), 0.28)  # noqa: E731
    cork = lambda u, v: capsule(u, v, at(0.82), at(0.95), 1.25)  # noqa: E731
    return [*hand_layers(*SKIN_TONES),
            glow(liquid, flat((80, 255, 110, 120)), 2.6), outline(glass, (14, 40, 26, 240)),
            fill(glass, flat((210, 245, 225, 90))),
            fill(liquid, linear((3, 13), (9, 7), [(0, (40, 170, 60)), (1, (120, 255, 130))])),
            fill(shine, flat((255, 255, 255, 200))), fill(cork, bevel(flat((176, 122, 70)), (90, 56, 30), 0.9, 0.5))]


def healing_picture():
    # 99: a glowing pale blue hand with a blue heart in its palm.
    heart = placed(lambda x, y: min(circle(x, y, -0.5, -0.25, 0.62), circle(x, y, 0.5, -0.25, 0.62),
                                    polygon_signed(x, y, [(-1.08, 0.05), (1.08, 0.05), (0, 1.15)])), 8.1, 11.2, 2.3)
    return [*hand_layers((240, 250, 255), (150, 200, 250), (70, 120, 210), (150, 205, 255, 150)),
            fill(heart, linear((8, 9), (8, 14), [(0, (80, 150, 245)), (1, (36, 86, 200))]))]


def cold_picture():
    # 56: a white snowflake edged in ice blue, in a cold glow.
    return [glow(snowflake, flat((140, 210, 255, 150)), 3.0), outline(snowflake, (20, 20, 70, 220), 0.5),
            fill(snowflake, bevel(flat((255, 255, 255)), (150, 205, 250), 1.0, 0.7))]


def disease_picture():
    # 41: a skin-toned hand with a bone skull at its lower right.
    return hand_layers(*SKIN_TONES) + skull_layers(11.6, 11.9)


def phantom_armor_picture():
    # 1: a silver heater shield, its left half lighter as in heraldry, a pink-white crossed sparkle at its lower left.
    return [glow(heater_shield, flat((220, 150, 255, 90)), 2.5), outline(heater_shield),
            shaded(heater_shield, STEEL, (6, 2), (13, 14), 1.1, 0.55),
            fill(lambda u, v: max(heater_shield(u, v), u - 9.2), flat((255, 255, 255, 70))),
            *sparkle_layers(4.2, 11.6, 4.0, crossed=True)]


def banishing_picture():
    # 153: the open hand raised, glowing red, turning away the undead and summoned.
    return hand_layers((255, 226, 226), (240, 120, 124), (150, 40, 50), (255, 110, 120, 150))


def summoned_weapon_picture():
    # 38, the pets' summoning: a steel sword floating over a hand held out palm up, in a pink glow.
    return sword_layers((4.4, 8.6), (14.6, 1.2), (255, 180, 240, 150)) + offered_hand_layers()


def summoned_food_picture():
    # 37, summoned food, drink and items: a glowing pink-white orb over a hand held out palm up.
    orb = lambda u, v: circle(u, v, 8, 5.4, 2.7)  # noqa: E731
    rays = lambda u, v: polygon_signed(u - 8, v - 5.4, four_point_star(0, 0, 5.2, 0.7))  # noqa: E731
    return [glow(orb, flat((255, 160, 240, 170)), 3.4), fill(rays, flat((255, 220, 250, 190))),
            fill(orb, radial((7.4, 4.8), 3.0, [(0, (255, 255, 255)), (0.5, (255, 214, 250)), (1, (230, 120, 220))])),
            *offered_hand_layers()]


def haste_picture():
    # 16: a silver sword swept up to the right, the middle of its blade near the tile's, with a white feathered wing
    # springing from each edge there and sweeping back toward the hilt, and speed streaks behind. duxaUI's butterfly
    # wings behind an upright sword were tried (the user didn't like them), and wings at the guard were moved here.
    base, tip = (4.0, 12.0), (13.4, 2.6)
    middle = (base[0] + (tip[0] - base[0]) * 0.46, base[1] + (tip[1] - base[1]) * 0.46)
    streaks = lambda u, v: min(capsule(u, v, (0.4 + k, 11.2 + k), (2.6 + k, 9.0 + k), 0.3) for k in (0, 1.8))  # noqa: E731
    layers = [fill(streaks, flat((200, 225, 255, 140)))]
    feathers = []
    for side, away in ((-1, 225), (1, 45)):  # up and left, then down and right: out from the blade's edge
        start = (middle[0] + 0.75 * side, middle[1] + 0.75 * side)
        for k, (reach, width) in enumerate(((6.0, 1.25), (5.2, 1.1), (4.2, 0.95))):
            a = math.radians(away + side * 26 * k)  # each further feather turned toward the hilt
            feathers.append((start, (start[0] + reach * math.cos(a), start[1] + reach * math.sin(a)), width, 0.4))
    for f in reversed(feathers):
        feather = lambda u, v, f=f: tapered(u, v, *f)  # noqa: E731
        layers += [outline(feather, (30, 40, 70, 220), 0.5), shaded(feather, FEATHER, f[0], f[1], 0.7, 0.45)]
    return layers + sword_layers(base, tip, (210, 230, 255, 120), half=0.95, guard=2.0, grip=1.7)


def slow_picture():
    # 17: a white clock face with a dark rim, its hour marks and two hands, the long one a small sword.
    face = lambda u, v: circle(u, v, 8, 8.4, 6.5)  # noqa: E731
    marks = lambda u, v: min(  # noqa: E731
        capsule(u, v, (8 + 4.4 * math.cos(a), 8.4 + 4.4 * math.sin(a)), (8 + 5.4 * math.cos(a), 8.4 + 5.4 * math.sin(a)),
                0.25 if k % 3 else 0.42) for k in range(12) for a in [math.radians(30 * k - 90)])
    blade, _, guard_bar, grip_bar = sword_parts((8, 9.6), (8, 3.0), half=0.7, guard=1.4, grip=1.2)
    ink = flat((60, 64, 80))
    return [glow(face, flat((255, 200, 200, 110)), 2.2), outline(face),
            fill(face, bevel(radial((7, 7), 7, [(0, (255, 252, 248)), (1, (226, 214, 208))]), (150, 110, 110), 1.2, 0.5)),
            fill(lambda u, v: abs(face(u, v) + 0.45) - 0.45, flat((90, 24, 28))), fill(marks, flat((60, 20, 22))),
            fill(lambda u, v: capsule(u, v, (8, 8.4), (10.6, 10.0), 0.55), flat((50, 24, 26))),
            fill(blade, ink), fill(guard_bar, ink), fill(grip_bar, ink),
            fill(lambda u, v: circle(u, v, 8, 8.4, 0.9), flat((50, 24, 26)))]


def run_speed_picture():
    # 4, Spirit of Wolf and its kind: a brown leather boot, toe down to the left, with a white wing sweeping up from
    # the top of its shaft.
    boot = lambda u, v: polygon_signed(u, v, [(6.0, 3.0), (10.4, 3.0), (10.4, 13.2), (10.9, 14.8), (1.4, 14.8),  # noqa: E731
                                              (1.4, 12.6), (3.0, 11.4), (5.8, 10.0)]) - 0.35
    feathers = (((10.0, 7.4), (15.0, 1.4), 1.25, 0.45), ((10.0, 8.9), (15.3, 4.4), 1.15, 0.42),
                ((10.0, 10.3), (15.0, 7.4), 1.0, 0.4))
    wing = lambda u, v: min(tapered(u, v, *f) for f in feathers)  # noqa: E731
    layers = [glow(wing, flat((230, 255, 230, 110)), 2.5), outline(boot), shaded(boot, LEATHER, (4, 4), (10, 15)),
              fill(lambda u, v: max(boot(u, v), v - 4.7), flat((70, 40, 18, 150))),  # the cuff
              fill(lambda u, v: max(boot(u, v), 13.7 - v), flat((50, 28, 12, 220)))]  # the sole
    for f in reversed(feathers):
        feather = lambda u, v, f=f: tapered(u, v, *f)  # noqa: E731
        layers += [outline(feather, (40, 50, 60, 220), 0.5), shaded(feather, FEATHER, f[0], f[1], 0.8, 0.45)]
    return layers


def mesmerize_picture():
    # 35: a closed eye in skin, a brow over it, the fold of its lid, the lash line curving down across it and long lashes
    # curling down and out from it, in a soft purple glow. Only the upper lid, with the lashes hanging past it, looked
    # flat; a hypnotic spiral was offered as well.
    lid = lambda u, v: max(circle(u, v, 8, 13.8, 7.9), circle(u, v, 8, 5.6, 6.4))  # noqa: E731
    fold = lambda u, v: arc_distance(u, v, 8, 11.8, 6.8, 228, 312) - 0.28  # noqa: E731
    lash_line = lambda u, v: arc_distance(u, v, 8, 5.6, 6.4, 38, 142) - 0.45  # noqa: E731
    brow = lambda u, v: arc_distance(u, v, 8, 14.8, 11.0, 238, 302) - 0.55  # noqa: E731
    lashes = []
    for degrees, bend in ((50, -1.3), (66, -0.8), (82, -0.3), (98, 0.3), (114, 0.8), (130, 1.3)):
        a = math.radians(degrees)
        root = (8 + 6.4 * math.cos(a), 5.6 + 6.4 * math.sin(a))
        lashes.append((root, (root[0] + 2.2 * math.cos(a) + bend, root[1] + 2.2 * math.sin(a) + 0.4)))
    lash = lambda u, v: min(tapered(u, v, a, b, 0.4, 0.14) for a, b in lashes)  # noqa: E731
    lit, mid, rim = SKIN_TONES
    return [glow(lambda u, v: circle(u, v, 8, 8.5, 5.5), flat((230, 170, 255, 70)), 2.5), outline(lid),
            fill(lid, bevel(linear((8, 4.6), (8, 11.6), [(0, lit), (1, mid)]), rim, 1.1, 0.5)),
            fill(inside(lid, fold), flat((*rim, 190))), fill(lash, flat((44, 22, 30))), fill(lash_line, flat((44, 22, 30))),
            fill(brow, flat((96, 60, 44)))]


def invisibility_picture():
    # 18: an open eye, white with a shadow under the lid, a blue-grey iris, the pupil and a highlight, in skin lids.
    iris = lambda u, v: max(circle(u, v, 8, 8.2, 2.9), almond(u, v))  # noqa: E731
    upper_lid = lambda u, v: abs(circle(u, v, 8, 10.42, 7.22)) - 0.55 if v < 8.2 else 1  # noqa: E731
    return [outline(almond),
            fill(almond, linear((8, 3), (8, 13), [(0, (190, 186, 184)), (0.4, (250, 250, 250)), (1, (220, 220, 224))])),
            fill(iris, radial((8, 8.2), 2.9, [(0, (70, 90, 120)), (0.6, (110, 140, 180)), (1, (60, 76, 100))])),
            fill(lambda u, v: circle(u, v, 8, 8.2, 1.2), flat((16, 16, 22))),
            fill(lambda u, v: circle(u, v, 9.1, 7.2, 0.7), flat((255, 255, 255, 230))),
            fill(upper_lid, flat(SKIN_TONES[1])),
            fill(lambda u, v: abs(almond(u, v) + 0.25) - 0.4, flat((*SKIN_TONES[2], 240)))]


def root_picture():
    # 117: a leather boot held fast, roots coiled round its ankle and growing down into the ground beside it. Roots
    # alone, spreading down from a stub of trunk, read as a tree (the user's pick over a tangle of roots after duxaUI's).
    boot = lambda u, v: polygon_signed(u, v, [(5.0, 1.2), (9.8, 1.2), (9.8, 10.6), (14.2, 11.4), (15.0, 12.8),  # noqa: E731
                                              (15.0, 14.2), (4.6, 14.2), (5.0, 9.0)]) - 0.35
    coils = [curve((2.2, 5.0), (7.4, 3.4), (11.4, 6.0), 0.75, 0.6), curve((11.4, 6.0), (7.2, 8.8), (3.0, 7.8), 0.65, 0.55),
             curve((3.0, 7.8), (1.6, 11.0), (2.4, 15.4), 0.6, 0.25), curve((11.2, 6.2), (13.6, 7.2), (13.8, 9.6), 0.4, 0.18),
             curve((3.4, 5.0), (1.2, 3.6), (0.8, 1.2), 0.5, 0.2)]
    roots = lambda u, v: min(coil(u, v) for coil in coils)  # noqa: E731
    return [glow(boot, flat((120, 200, 110, 60)), 2.0), outline(boot), shaded(boot, LEATHER, (5, 2), (12, 14)),
            fill(lambda u, v: max(boot(u, v), 13.1 - v), flat((50, 28, 12, 220))),  # the sole
            glow(roots, flat((120, 200, 110, 50)), 2.0), outline(roots, width=0.55),
            fill(roots, bevel(linear((5, 1), (11, 15), [(0, (184, 128, 74)), (1, (116, 72, 38))]), (58, 32, 14), 0.7, 0.55))]


# Batch 2: hands, body and mind. More objects the pictures share first.

WOOD = ((204, 158, 100), (146, 100, 56), (70, 44, 20))
LIPS = ((252, 128, 138), (196, 34, 54), (100, 10, 24))
CAT_FUR = ((255, 224, 140), (216, 160, 62), (110, 70, 20))
RED_HEART = ((255, 176, 176), (228, 40, 60), (110, 6, 20))
DRAINED_HEART = ((130, 96, 104), (72, 36, 46), (30, 8, 16))
BRAINS = {  # (light, mid, rim) of a brain in each of duxaUI's colors
    'lavender': ((220, 204, 252), (150, 116, 214), (66, 44, 128)),
    'pink': ((252, 208, 216), (214, 138, 158), (116, 58, 78)),
    'blue': ((208, 224, 255), (120, 150, 232), (44, 62, 150)),
    'pale': ((244, 232, 236), (194, 164, 174), (100, 76, 86)),
}


def union(*shapes):
    """The shapes as one: each point's distance to the nearest."""
    return lambda u, v: min(shape(u, v) for shape in shapes)


def tilted(shape, degrees, cx=8.0, cy=8.0):
    """shape turned by degrees about (cx, cy)."""
    return lambda u, v: shape(*turned(u, v, degrees, cx, cy))


def star(cx, cy, points, outer, inner):
    """A star of points points, outer to their tips and inner to the notches between, one tip straight up."""
    corners = [(cx + (outer if k % 2 == 0 else inner) * math.cos(math.radians(-90 + 180 * k / points)),
                cy + (outer if k % 2 == 0 else inner) * math.sin(math.radians(-90 + 180 * k / points)))
               for k in range(2 * points)]
    return lambda u, v: polygon_signed(u, v, corners)


def heart(cx, cy, scale):
    """A heart centered about (cx, cy), 2.24 scales across."""
    def shape(u, v):
        x, y = (u - cx) / scale, (v - cy) / scale
        return min(circle(x, y, -0.5, -0.25, 0.62), circle(x, y, 0.5, -0.25, 0.62),
                   polygon_signed(x, y, [(-1.08, 0.05), (1.08, 0.05), (0, 1.15)])) * scale
    return shape


def glossy(shape, palette, halo, shine):
    """shape as a glossy object in palette: lit toward its shine, a (cx, cy, rx, ry, degrees) highlight, with a halo."""
    lit, mid, rim = palette
    highlight = lambda u, v: tilted_ellipse(u, v, *shine)  # noqa: E731
    return [*([glow(shape, flat(halo), 2.4)] if halo else []), outline(shape),
            fill(shape, bevel(radial((shine[0] + 0.6, shine[1] + 0.6), 6, [(0, lit), (1, mid)]), rim, 1.0, 0.6)),
            fill(inside(shape, highlight), flat((255, 255, 255, 170)))]


def skin_fill(shape, light=(4, 3), dark=(12, 14), width=1.1):
    lit, mid, rim = SKIN_TONES
    return fill(shape, bevel(linear(light, dark, [(0, lit), (1, mid)]), rim, width, 0.5))


def glowing_hand(lit, mid, rim, halo, sparkle=None):
    """The open hand in a spell's glowing colors, with a sparkle at its fingertips when sparkle (its rim color) is given."""
    return hand_layers(lit, mid, rim, halo) + (sparkle_layers(12.8, 3.0, 2.8, rim=sparkle) if sparkle else [])


def rejuvenation_picture():
    # 0: the healing hand without its heart, glowing blue, a sparkle at its fingertips.
    return glowing_hand((226, 238, 255), (110, 160, 250), (40, 80, 190), (130, 180, 255, 160), (170, 210, 255))


def regeneration_picture():
    # 118: a pale blue hand, glowing.
    return glowing_hand((242, 248, 255), (172, 206, 250), (80, 120, 200), (170, 210, 255, 140))


def complete_heal_picture():
    # 119: a paler lavender hand, glowing brighter, with a sparkle.
    return glowing_hand((250, 246, 255), (200, 190, 252), (110, 100, 200), (210, 200, 255, 180), (230, 220, 255))


def flexed_arm(u, v):
    # The upper arm across the bottom from the left, the bicep bulging over it, the elbow at the right, the forearm
    # standing up from it and the fist clenched at the top, its fingers toward the bicep. Without the bulge and the
    # fist's fingers it read as a leg.
    return min(tapered(u, v, (-0.4, 13.0), (10.0, 12.6), 2.3, 2.2), ellipse_signed(u, v, 5.8, 10.0, 3.9, 3.1),
               circle(u, v, 11.2, 12.2, 2.3), tapered(u, v, (11.6, 11.4), (11.2, 5.8), 2.35, 2.0),
               rounded_rect_distance(u, v, 8.2, 0.9, 13.8, 6.4, 2.1))


def strengthen_picture():
    # 6: the flexed arm, in a purple-white glow.
    lit, mid, rim = SKIN_TONES
    under_bicep = curve((2.6, 11.6), (6.2, 13.0), (9.6, 11.2), 0.3, 0.22)
    elbow = curve((9.4, 9.6), (9.8, 10.8), (9.4, 11.6), 0.26, 0.2)
    fingers = lambda u, v: min(segment_distance(u, v, (8.4, y), (10.8, y)) for y in (2.4, 3.7, 5.0)) - 0.2  # noqa: E731
    thumb = lambda u, v: tapered(u, v, (9.2, 1.6), (12.6, 2.6), 0.75, 0.6)  # noqa: E731
    shine = lambda u, v: tilted_ellipse(u, v, 5.0, 8.4, 2.0, 0.7, -12)  # noqa: E731
    return [glow(flexed_arm, flat((230, 190, 255, 140)), 3.0), outline(flexed_arm),
            fill(flexed_arm, bevel(linear((4, 7), (12, 15), [(0, lit), (1, mid)]), rim, 1.2, 0.55)),
            fill(inside(flexed_arm, under_bicep), flat((*rim, 200))), fill(inside(flexed_arm, elbow), flat((*rim, 170))),
            fill(inside(flexed_arm, fingers), flat((*rim, 200))),
            outline(thumb, (*rim, 220), 0.4), shaded(thumb, SKIN_TONES, (9, 1), (12, 3), 0.6, 0.45),
            fill(shine, flat((255, 255, 255, 120)))]


def weaken_picture():
    # 7: the arm gone limp, sagging from the left, the forearm hanging from the elbow, the hand open, red drops falling,
    # in a red glow. Strengthen's flexed arm in red (duxaUI's) was redrawn at the user's call; the user picked this
    # over the arm drained grey with a red arrow down, and with red wisps drawn out of it.
    arm = union(lambda u, v: tapered(u, v, (-0.6, 6.2), (9.8, 7.0), 2.1, 1.9),
                lambda u, v: ellipse_signed(u, v, 5.0, 7.8, 3.4, 1.9), lambda u, v: circle(u, v, 10.6, 7.6, 1.95),
                lambda u, v: tapered(u, v, (10.8, 8.0), (11.8, 12.4), 1.85, 1.55),
                lambda u, v: ellipse_signed(u, v, 12.0, 13.4, 1.7, 1.5),
                *[lambda u, v, x=x: tapered(u, v, (x, 14.0), (x - 0.5, 15.6), 0.48, 0.38) for x in (11.0, 12.0, 13.0)])
    drops = lambda u, v: min(circle(u, v, x, y, r) for x, y, r in ((6.0, 11.4, 0.55), (4.2, 12.8, 0.4), (7.6, 13.6, 0.45)))  # noqa: E731
    elbow = curve((9.4, 5.4), (10.2, 6.8), (9.6, 8.4), 0.26, 0.2)
    return [glow(arm, flat((255, 120, 120, 150)), 3.0), outline(arm), skin_fill(arm, (3, 4), (12, 15)),
            fill(inside(arm, elbow), flat((*SKIN_TONES[2], 180))), fill(drops, flat((255, 90, 90, 200)))]


def dexterity_picture():
    # 8: a sword balanced flat across the tip of a raised finger. duxaUI's hand pinching an upright sword's pommel read
    # poorly; the user picked this over a hand juggling three balls and a dagger spinning over a palm.
    fist = lambda u, v: rounded_rect_distance(u, v, 4.8, 9.6, 11.4, 15.8, 2.2)  # noqa: E731
    finger = lambda u, v: tapered(u, v, (7.2, 10.4), (7.4, 5.8), 1.0, 0.85)  # noqa: E731
    curled = lambda u, v: min(circle(u, v, 10.8, y, 1.05) for y in (10.8, 12.5, 14.2))  # noqa: E731
    thumb = lambda u, v: tapered(u, v, (5.2, 13.0), (8.8, 11.4), 0.95, 0.8)  # noqa: E731
    hand = union(fist, finger, curled)
    lit, mid, rim = SKIN_TONES
    return [glow(lambda u, v: segment_distance(u, v, (1, 4.4), (15, 4.4)) - 1, flat((240, 210, 255, 100)), 2.4),
            *sword_layers((4.0, 4.4), (15.4, 4.4), (240, 210, 255, 90), half=0.85, guard=1.7, grip=1.4),
            outline(hand), skin_fill(hand, (5, 6), (11, 16)), outline(curled, (*rim, 210), 0.35),
            fill(curled, bevel(linear((10, 10), (11, 15), [(0, lit), (1, mid)]), rim, 0.7, 0.5)),
            outline(thumb, (*rim, 230), 0.4), fill(thumb, bevel(linear((5, 12), (9, 12), [(0, lit), (1, mid)]), rim, 0.7, 0.45))]


def agility_picture():
    # 9: a spotted golden cat mid-leap.
    body = union(lambda u, v: tilted_ellipse(u, v, 7.6, 8.2, 4.9, 1.9, -12), lambda u, v: ellipse_signed(u, v, 11.0, 7.4, 2.0, 1.8),
                 lambda u, v: circle(u, v, 13.3, 5.8, 1.7),
                 lambda u, v: polygon_signed(u, v, [(12.2, 4.8), (12.6, 3.0), (13.4, 4.4)]) - 0.15,
                 lambda u, v: polygon_signed(u, v, [(13.6, 4.4), (14.6, 3.0), (14.8, 4.9)]) - 0.15,
                 lambda u, v: ellipse_signed(u, v, 14.7, 6.4, 1.0, 0.75),
                 lambda u, v: tapered(u, v, (11.6, 8.4), (15.3, 10.2), 0.72, 0.42),
                 lambda u, v: tapered(u, v, (11.0, 8.8), (14.2, 11.6), 0.66, 0.4),
                 lambda u, v: tapered(u, v, (4.4, 9.0), (0.8, 12.6), 0.95, 0.45),
                 lambda u, v: tapered(u, v, (5.2, 9.4), (2.4, 13.8), 0.85, 0.4),
                 curve((3.4, 7.4), (1.0, 5.8), (1.4, 3.0), 0.55, 0.3))
    spots = lambda u, v: min(circle(u, v, x, y, r) for x, y, r in  # noqa: E731
                             ((6.0, 7.6, 0.5), (8.2, 7.2, 0.45), (9.8, 8.4, 0.45), (7.0, 9.0, 0.4), (4.8, 8.7, 0.4)))
    lit, mid, rim = CAT_FUR
    return [glow(body, flat((255, 220, 150, 110)), 2.4), outline(body),
            fill(body, bevel(linear((8, 5), (8, 12), [(0, lit), (1, mid)]), rim, 0.9, 0.5)),
            fill(inside(body, spots), flat((90, 56, 20, 200))), fill(lambda u, v: circle(u, v, 13.9, 5.5, 0.32), flat((30, 20, 10)))]


BIG_HEART = heart(8, 7.7, 6.3)


def stamina_picture():
    # 10: a glossy blue heart.
    return glossy(BIG_HEART, ((170, 212, 255), (40, 118, 240), (10, 40, 120)), (120, 180, 255, 130), (5.4, 4.8, 1.7, 0.85, -35))


def vampiric_embrace_picture():
    # 140: a glossy black heart in a red glow.
    return glossy(BIG_HEART, ((120, 116, 124), (34, 30, 36), (0, 0, 0)), (255, 90, 90, 110), (5.4, 4.8, 1.7, 0.85, -35))


def brain(u, v):
    # A brain from the side: the rounded cerebrum, the temporal lobe under it, the cerebellum and the brainstem.
    return min(ellipse_signed(u, v, 8.0, 7.0, 6.6, 4.5), ellipse_signed(u, v, 4.4, 8.4, 3.6, 3.4),
               ellipse_signed(u, v, 11.0, 8.6, 3.8, 3.0), ellipse_signed(u, v, 7.6, 10.4, 4.2, 2.0),
               ellipse_signed(u, v, 11.6, 11.4, 2.4, 1.6), tapered(u, v, (9.8, 11.0), (10.4, 14.4), 1.0, 0.8))


# Its grooves: short and wavy all over, none long enough to read as a line on a face (a few long ones did).
BRAIN_FOLDS = union(
    curve((2.6, 7.6), (3.2, 5.2), (4.8, 5.8), 0.22, 0.2), curve((4.8, 5.8), (5.6, 3.6), (7.4, 4.4), 0.22, 0.2),
    curve((7.8, 3.2), (8.4, 5.2), (10.0, 4.4), 0.22, 0.2), curve((10.0, 4.4), (11.8, 3.8), (12.4, 5.6), 0.22, 0.2),
    curve((13.0, 6.2), (12.0, 7.4), (13.6, 8.6), 0.22, 0.2), curve((4.2, 7.8), (5.8, 6.4), (6.6, 8.0), 0.22, 0.2),
    curve((6.6, 8.0), (7.6, 9.2), (8.6, 7.6), 0.22, 0.2), curve((8.8, 5.8), (10.2, 7.0), (9.6, 8.6), 0.22, 0.2),
    curve((10.8, 7.6), (11.8, 9.0), (12.8, 9.4), 0.22, 0.2), curve((3.2, 9.6), (5.8, 10.8), (9.0, 9.8), 0.3, 0.26),
    curve((2.4, 10.4), (3.0, 11.2), (2.6, 11.8), 0.2, 0.18), curve((5.4, 11.4), (6.8, 11.2), (7.6, 12.0), 0.2, 0.18),
    curve((10.4, 11.0), (11.8, 10.8), (13.4, 11.6), 0.18, 0.16), curve((10.8, 12.2), (12.0, 12.0), (13.0, 12.6), 0.18, 0.16))


def brain_layers(palette, halo, sparkle=None):
    """A brain in one of BRAINS' colors, in a halo, with a sparkle at its top left when sparkle (its rim color) is given."""
    lit, mid, rim = BRAINS[palette]
    return [glow(brain, flat(halo), 2.6), outline(brain),
            fill(brain, bevel(linear((5, 3), (11, 13), [(0, lit), (1, mid)]), rim, 1.1, 0.5)),
            fill(inside(brain, BRAIN_FOLDS), flat((*rim, 190))),
            *(sparkle_layers(4.2, 3.6, 3.4, rim=sparkle) if sparkle else [])]


def brilliance_picture():
    # 11: a lavender brain.
    return brain_layers('lavender', (200, 170, 255, 110))


def feeblemind_picture():
    # 12: a pink brain in a red glow.
    return brain_layers('pink', (255, 140, 140, 110))


def insight_picture():
    # 13: a blue brain with a sparkle.
    return brain_layers('blue', (150, 190, 255, 120), (190, 220, 255))


def mind_cloud_picture():
    # 14: a pink brain with a sparkle, in a red glow.
    return brain_layers('pink', (255, 150, 150, 110), (255, 200, 210))


def sathirs_gaze_picture():
    # 36: a pale, faded brain.
    return brain_layers('pale', (255, 200, 230, 90))


def mana_sieve_picture():
    # 40: a pale brain with a sparkle, in a violet glow.
    return brain_layers('pale', (200, 170, 255, 110), (230, 210, 255))


def charisma_picture():
    # 15: a gold crown, five points with balls on their tips, red, blue and green jewels on its band.
    points = [(2.6, 10.6), (2.2, 4.4), (4.4, 7.8), (5.2, 3.8), (6.6, 7.6), (8.0, 3.0), (9.4, 7.6), (10.8, 3.8),
              (11.6, 7.8), (13.8, 4.4), (13.4, 10.6)]
    crown = union(lambda u, v: polygon_signed(u, v, points) - 0.2,
                  lambda u, v: rounded_rect_distance(u, v, 2.4, 10.0, 13.6, 13.6, 0.7),
                  lambda u, v: min(circle(u, v, x, y, r) for x, y, r in
                                   ((2.2, 4.0, 0.95), (5.2, 3.4, 0.75), (8.0, 2.4, 1.05), (10.8, 3.4, 0.75), (13.8, 4.0, 0.95))))
    band = lambda u, v: min(abs(v - 10.3), abs(v - 13.3)) - 0.2  # noqa: E731
    layers = [glow(crown, flat((255, 220, 130, 120)), 2.6), outline(crown),
              fill(crown, bevel(linear((5, 2), (11, 14), [(0, GOLD[0]), (1, GOLD[1])]), GOLD[2], 1.0, 0.5)),
              fill(inside(crown, band), flat((*GOLD[2], 170)))]
    for x, y, r, rgb in ((8.0, 11.8, 1.0, (230, 40, 60)), (5.0, 11.8, 0.75, (60, 110, 240)), (11.0, 11.8, 0.75, (40, 190, 90))):
        jewel = lambda u, v, x=x, y=y, r=r: circle(u, v, x, y, r)  # noqa: E731
        layers += [outline(jewel, width=0.4),
                   fill(jewel, radial((x - 0.3, y - 0.3), r * 1.3, [(0, (255, 255, 255)), (0.4, rgb), (1, rgb)]))]
    return layers


def stun_picture():
    # 25: a steel war hammer with a gold band, swinging down to the left into a bright impact flash. duxaUI's fist was
    # redrawn at the user's call; the user picked this over a fist punching into a burst and a ring of dizzy stars.
    head = tilted(lambda u, v: rounded_rect_distance(u, v, 2.8, 1.8, 13.2, 6.0, 1.0), 32, 8, 9)
    handle = tilted(lambda u, v: capsule(u, v, (8.0, 5.0), (8.0, 15.0), 0.85), 32, 8, 9)
    band = tilted(lambda u, v: rounded_rect_distance(u, v, 6.8, 1.2, 9.2, 6.6, 0.4), 32, 8, 9)
    flash = star(3.0, 10.4, 8, 3.6, 1.4)
    return [glow(flash, flat((255, 220, 120, 170)), 2.2),
            fill(flash, radial((3.0, 10.4), 3.6, [(0, (255, 255, 230)), (1, (255, 180, 70))])),
            outline(handle), shaded(handle, WOOD, (6, 6), (12, 15), 0.7, 0.5),
            glow(head, flat((255, 200, 200, 90)), 2.0), outline(head), shaded(head, STEEL, (3, 2), (12, 7), 1.0, 0.55),
            outline(band, width=0.4), shaded(band, GOLD, (7, 1), (9, 7), 0.6, 0.45)]


def puppet_control_layers():
    # A marionette's wooden control: a long bar with a short one across it.
    bar = lambda u, v: capsule(u, v, (1.8, 3.6), (14.2, 3.0), 0.8)  # noqa: E731
    cross = lambda u, v: capsule(u, v, (6.6, 0.8), (9.6, 6.4), 0.7)  # noqa: E731
    return [outline(bar), shaded(bar, WOOD, (2, 2), (14, 4), 0.7, 0.5), outline(cross), shaded(cross, WOOD, (6, 1), (10, 6), 0.7, 0.5)]


def charm_picture():
    # 26: a marionette's control, its strings hanging down.
    strings = union(curve((2.4, 4.0), (2.0, 9.0), (3.0, 14.8), 0.2, 0.2), curve((5.6, 3.8), (6.4, 9.0), (5.8, 13.4), 0.2, 0.2),
                    curve((10.4, 3.6), (9.8, 9.0), (10.6, 14.2), 0.2, 0.2), curve((13.6, 3.4), (14.2, 8.4), (13.2, 13.0), 0.2, 0.2))
    return [fill(strings, flat((30, 22, 26))), *puppet_control_layers()]


def dominate_undead_picture():
    # 27: the control, its strings holding up a skull.
    strings = union(*[lambda u, v, a=a, b=b: segment_distance(u, v, a, b) - 0.18 for a, b in
                      (((2.4, 4.0), (6.4, 9.0)), ((5.8, 3.8), (7.2, 8.6)), ((10.4, 3.6), (8.8, 8.6)), ((13.6, 3.4), (9.8, 9.2)))])
    return [fill(strings, flat((30, 22, 26))), *puppet_control_layers(), *skull_layers(8.0, 11.4, 1.05)]


def pointing_hand(u, v):
    # A hand from the left pointing right: the curled fingers' fist, the index finger straight out, the wrist.
    return min(rounded_rect_distance(u, v, 1.2, 6.8, 8.8, 12.8, 2.3), tapered(u, v, (6.8, 8.0), (15.0, 7.6), 1.05, 0.9),
               tapered(u, v, (-1.0, 10.4), (2.0, 10.0), 1.9, 1.9))


def mystic_shielding_picture():
    # 82: the pointing hand with a white sparkle behind it.
    thumb = lambda u, v: tapered(u, v, (4.2, 7.6), (9.0, 9.2), 0.95, 0.8)  # noqa: E731
    creases = lambda u, v: min(segment_distance(u, v, (6.2, y), (8.6, y + 0.2)) for y in (10.2, 11.6)) - 0.2  # noqa: E731
    rim = SKIN_TONES[2]
    return [glow(pointing_hand, flat((255, 230, 255, 110)), 3.0), *sparkle_layers(3.6, 3.6, 3.2, rim=(240, 200, 255)),
            outline(pointing_hand), skin_fill(pointing_hand, (4, 6), (10, 13)),
            fill(inside(pointing_hand, creases), flat((*rim, 190))),
            outline(thumb, (*rim, 230), 0.45), shaded(thumb, SKIN_TONES, (4, 7), (9, 9.4))]


def life_stream(start, bend, end, width=0.75):
    """A stream of life, dark red where it's drawn out to bright where it arrives, with drops flung from it."""
    stream = curve(start, bend, end, width, width * 0.55)
    drops = lambda u, v: min(circle(u, v, x, y, r) for x, y, r in  # noqa: E731
                             ((start[0] + (bend[0] - start[0]) * 0.4 - 1.0, start[1] + (bend[1] - start[1]) * 0.4 + 0.9, 0.4),
                              (bend[0] + 0.8, bend[1] - 0.9, 0.35)))
    return [glow(stream, flat((255, 60, 70, 170)), 1.8),
            fill(stream, linear(start, end, [(0, (150, 10, 30)), (1, (255, 110, 110))])), fill(drops, flat((230, 40, 60)))]


def lifetap_picture():
    # 47, taking an enemy's life to give it to you: a drained, cracked dark heart at the lower left, its life flowing
    # in a red stream into a bright heart at the top right. duxaUI's pointing hand didn't say so (the user); a hand
    # taking in the stream and an enemy's skull giving it were offered too.
    drained, bright = heart(4.4, 10.8, 3.0), heart(11.0, 5.8, 4.0)
    crack = lambda u, v: max(min(capsule(u, v, (4.2, 8.8), (4.8, 10.4), 0.2), capsule(u, v, (4.8, 10.4), (4.0, 12.2), 0.2)), drained(u, v))  # noqa: E731
    return [*glossy(drained, DRAINED_HEART, None, (3.4, 9.8, 0.9, 0.45, -35)), fill(crack, flat((20, 4, 8))),
            *life_stream((5.8, 9.2), (6.2, 5.2), (8.4, 5.6)),
            *glossy(bright, RED_HEART, (255, 90, 100, 150), (9.6, 4.4, 1.1, 0.55, -35))]


def eyeball_layers(cx, cy, r):
    """An eyeball looking out and a little right: the white shaded round, a green iris, the pupil and a glint."""
    ball = lambda u, v: circle(u, v, cx, cy, r)  # noqa: E731
    ix, iy = cx + 0.35 * r, cy + 0.1 * r
    iris = lambda u, v: max(circle(u, v, ix, iy, r * 0.46), ball(u, v))  # noqa: E731
    return [outline(ball),
            fill(ball, bevel(radial((cx - r * 0.3, cy - r * 0.35), r * 1.6, [(0, (255, 255, 255)), (0.6, (234, 228, 236)),
                                                                             (1, (176, 164, 184))]), (120, 100, 120), r * 0.35, 0.5)),
            fill(iris, radial((ix, iy), r * 0.46, [(0, (110, 210, 170)), (0.7, (40, 140, 110)), (1, (18, 70, 54))])),
            fill(lambda u, v: circle(u, v, ix + 0.1, iy + 0.05, r * 0.2), flat((10, 10, 14))),
            fill(lambda u, v: circle(u, v, ix - r * 0.2, iy - r * 0.2, r * 0.11), flat((255, 255, 255, 240)))]


def eye_of_zomm_picture():
    # 88, summoning an eye you see through: an eyeball rising glowing from a hand held out palm up. duxaUI's pointing
    # hand didn't say so (the user); a floating eyeball with a wisp and one on bat wings were offered too.
    return [glow(lambda u, v: circle(u, v, 8, 5.6, 3.6), flat((255, 230, 160, 160)), 3.0),
            *eyeball_layers(8, 5.6, 3.6), *offered_hand_layers()]


def animate_dead_picture():
    # 91: a hand held out, a skull glowing red over it.
    return [glow(lambda u, v: circle(u, v, 8, 6.6, 3.4), flat((255, 80, 80, 150)), 3.0),
            *skull_layers(8.0, 6.6, 1.2), *offered_hand_layers()]


def voice_graft_picture():
    # 95: full red lips, closed, with a shine on the lower one.
    upper = lambda u, v: max(ellipse_signed(u, v, 8, 8.6, 6.8, 2.8), v - 8.6, -circle(u, v, 8, 5.4, 1.1))  # noqa: E731
    lower = lambda u, v: max(ellipse_signed(u, v, 8, 8.6, 6.2, 3.5), 8.6 - v)  # noqa: E731
    lips = union(upper, lower)
    shine = lambda u, v: tilted_ellipse(u, v, 8.8, 10.4, 2.2, 0.55, -4)  # noqa: E731
    return [glow(lips, flat((255, 100, 110, 120)), 2.4), outline(lips),
            fill(lips, bevel(linear((8, 5), (8, 12), [(0, LIPS[0]), (1, LIPS[1])]), LIPS[2], 1.0, 0.5)),
            fill(curve((1.4, 8.5), (8, 9.2), (14.6, 8.5), 0.32, 0.32), flat((80, 8, 20))), fill(shine, flat((255, 255, 255, 150)))]


def call_of_the_hero_picture():
    # 102: a hand held out, a silver medallion on a purple ribbon over it, in a magenta glow.
    ribbon = union(lambda u, v: capsule(u, v, (5.4, 0.4), (7.6, 4.8), 0.6), lambda u, v: capsule(u, v, (10.6, 0.4), (8.4, 4.8), 0.6))
    medal = lambda u, v: circle(u, v, 8, 7.2, 2.7)  # noqa: E731
    emblem = lambda u, v: polygon_signed(u - 8, v - 7.2, four_point_star(0, 0, 1.9, 0.5))  # noqa: E731
    return [glow(medal, flat((255, 140, 240, 160)), 3.0), outline(ribbon), fill(ribbon, flat((140, 40, 160))),
            outline(medal), shaded(medal, STEEL, (6, 5), (10, 10), 1.0, 0.5), fill(emblem, flat((120, 126, 150))),
            *offered_hand_layers()]


def summon_corpse_picture():
    # 109: a hand held out, a wooden coffin over it with a gold cross on the lid.
    coffin = lambda u, v: polygon_signed(u, v, [(1.4, 6.0), (4.6, 4.0), (14.8, 5.0), (14.8, 8.8), (4.6, 9.8), (1.4, 7.8)]) - 0.2  # noqa: E731
    lid = lambda u, v: abs(coffin(u, v) + 0.95) - 0.2  # noqa: E731
    cross = union(lambda u, v: capsule(u, v, (5.4, 6.9), (8.4, 7.0), 0.3), lambda u, v: capsule(u, v, (6.4, 5.8), (6.4, 8.0), 0.3))
    return [glow(coffin, flat((210, 150, 255, 110)), 2.4), outline(coffin), shaded(coffin, WOOD, (3, 4), (13, 10), 0.9, 0.5),
            fill(inside(coffin, lid), flat((*WOOD[2], 170))), fill(cross, flat(GOLD[0])), *offered_hand_layers()]


def silence_picture():
    # 114: an ear, its folds shaded, with a small gold earring.
    ear = union(lambda u, v: ellipse_signed(u, v, 8.8, 6.6, 4.4, 5.6), lambda u, v: ellipse_signed(u, v, 7.6, 11.6, 2.6, 2.8))
    rim_fold = lambda u, v: arc_distance(u, v, 9.0, 6.8, 3.2, 150, 60) - 0.3  # noqa: E731
    inner_fold = curve((6.4, 5.2), (9.6, 4.2), (10.6, 7.6), 0.3, 0.25)
    bowl = lambda u, v: ellipse_signed(u, v, 8.6, 8.6, 1.5, 2.1)  # noqa: E731
    ring = lambda u, v: abs(circle(u, v, 7.2, 14.0, 0.9)) - 0.28  # noqa: E731
    rim = SKIN_TONES[2]
    return [glow(ear, flat((255, 170, 150, 100)), 2.4), outline(ear), skin_fill(ear, (6, 2), (11, 14), 1.2),
            fill(inside(ear, rim_fold), flat((*rim, 170))), fill(inside(ear, inner_fold), flat((*rim, 150))),
            fill(bowl, flat((*rim, 190))), fill(ring, flat(GOLD[1]))]


def illusion_picture():
    # 163: a gold masquerade eye mask with swept-up corners, purple feathers springing from one side, a sparkle.
    # duxaUI's bearded gold face mask was redrawn at the user's call; the user picked this over the comedy and tragedy
    # masks and a smooth gold face mask.
    mask = union(lambda u, v: tilted_ellipse(u, v, 5.0, 9.0, 3.8, 2.3, -14), lambda u, v: tilted_ellipse(u, v, 11.0, 9.0, 3.8, 2.3, 14),
                 lambda u, v: polygon_signed(u, v, [(0.6, 6.4), (2.6, 8.6), (1.4, 9.6)]),
                 lambda u, v: polygon_signed(u, v, [(15.4, 6.4), (13.4, 8.6), (14.6, 9.6)]))
    holes = union(lambda u, v: tilted_ellipse(u, v, 5.2, 9.2, 1.6, 0.8, -8), lambda u, v: tilted_ellipse(u, v, 10.8, 9.2, 1.6, 0.8, 8))
    layers = []
    for f in (((12.6, 7.4), (15.2, 1.2), 0.95, 0.3), ((12.0, 7.2), (12.8, 0.6), 0.95, 0.3), ((11.4, 7.4), (10.2, 1.2), 0.85, 0.28)):
        feather = lambda u, v, f=f: tapered(u, v, *f)  # noqa: E731
        layers += [outline(feather, width=0.4),
                   fill(feather, bevel(linear(f[0], f[1], [(0, (120, 50, 170)), (1, (220, 170, 255))]), (60, 20, 90), 0.6, 0.5))]
    return [*layers, glow(mask, flat((255, 220, 140, 120)), 2.2), outline(mask), shaded(mask, GOLD, (4, 7), (12, 11), 0.9, 0.5),
            fill(holes, flat((30, 18, 40))), *sparkle_layers(3.0, 3.4, 2.4, rim=(200, 220, 255))]


# Batch 3: shields and armor. Most are one steel shield with what duxaUI puts on or beside it.

GLASS_BLUE = ((214, 228, 255), (96, 116, 226), (30, 40, 120))
RED_METAL = ((255, 178, 150), (206, 64, 44), (90, 20, 10))
LAVENDER_METAL = ((236, 228, 255), (164, 144, 232), (60, 40, 120))
BLUE_METAL = ((214, 232, 255), (110, 150, 232), (40, 60, 140))
ROSE_METAL = ((255, 200, 214), (214, 80, 110), (100, 20, 40))
GREEN_SCALES = ((206, 242, 196), (96, 166, 96), (30, 70, 30))
ENAMEL = ((255, 255, 250), (222, 216, 204), (120, 110, 90))
GREY_FUR = ((222, 218, 212), (132, 126, 122), (54, 50, 50))
STONE = ((150, 150, 158), (70, 70, 78), (24, 24, 30))


def moved(shape, cx, cy, scale, center=(8.0, 8.0)):
    """shape, drawn round center on the grid, put at (cx, cy) at scale."""
    return lambda u, v: shape((u - cx) / scale + center[0], (v - cy) / scale + center[1]) * scale


def heater(cx=8.0, top=1.6, width=10.0, height=13.8):
    """A heater shield: a flat top and straight sides curving in to a point at the bottom."""
    half = width / 2
    right = [(cx + half, top), (cx + half, top + 0.406 * height), (cx + 0.864 * half, top + 0.625 * height),
             (cx + 0.432 * half, top + 0.828 * height)]
    points = [(cx, top + height)] + [(2 * cx - x, y) for x, y in right[::-1]] + right
    return lambda u, v: polygon_signed(u, v, points) - 0.3


SHIELD = heater()


def small_shield(cx, top, width):
    """A heater shield width across, to leave room for something beside it."""
    return heater(cx, top, width, width * 1.38)


def shield_layers(shape=SHIELD, palette=STEEL, halo=None, heraldry=True, cx=8.0):
    """A shield in a metal: lit from the top left to shadow at the bottom right, a darker rim band round it, a ridge
    down its middle and a shine along its left side, with a halo. heraldry=False leaves off the ridge and shine, for a
    shield with something painted on it. Without the rim band and the shading's dark end it looked like paper."""
    lit, mid, rim = palette
    return [*([glow(shape, flat(halo), 2.6)] if halo else []), outline(shape),
            fill(shape, bevel(linear((cx - 4, 1), (cx + 4, 15), [(0, lit), (0.55, mid), (1, rim)]), rim, 1.0, 0.45)),
            fill(inside(shape, lambda u, v: abs(shape(u, v) + 0.75) - 0.42), flat((*rim, 200))),
            *([fill(inside(shape, lambda u, v: capsule(u, v, (cx, 2.4), (cx, 13.6), 0.32)), flat((255, 255, 255, 110))),
               fill(inside(shape, lambda u, v: capsule(u, v, (cx - 3.2, 3.0), (cx - 2.6, 9.4), 0.5)), flat((255, 255, 255, 140)))]
              if heraldry else [])]


def burst_layers(cx, cy, size, rim=(200, 170, 255), halo=160):
    """A bright light: a big four-pointed star over a turned smaller one, white at its heart, in a glow of rim."""
    big = lambda u, v: polygon_signed(u - cx, v - cy, four_point_star(0, 0, size, size * 0.2))  # noqa: E731
    small = lambda u, v: polygon_signed((u - cx + v - cy) * math.sqrt(0.5), (v - cy - u + cx) * math.sqrt(0.5),  # noqa: E731
                                        four_point_star(0, 0, size * 0.62, size * 0.16))
    white = (255, 255, 255)
    return [glow(big, flat((*rim, halo)), size * 0.7), fill(small, radial((cx, cy), size * 0.6, [(0, white), (1, rim)])),
            fill(big, radial((cx, cy), size, [(0, white), (0.35, white), (1, rim)])),
            fill(lambda u, v: circle(u, v, cx, cy, size * 0.18), flat(white))]


def snowflake_layers(cx, cy, scale):
    """The cold picture's snowflake, small, at (cx, cy)."""
    flake = moved(snowflake, cx, cy, scale)
    return [glow(flake, flat((150, 210, 255, 150)), 1.6), outline(flake, (20, 20, 70, 220), 0.45),
            fill(flake, bevel(flat((255, 255, 255)), (150, 205, 250), 0.8, 0.6))]


def flame_layers(cx, cy, scale):
    """The fire picture's flame, small, at (cx, cy)."""
    fire = moved(flame, cx, cy, scale)
    heart = moved(lambda u, v: min(circle(u, v, 8, 11.5, 2.4), polygon_signed(u, v, [(5.7, 11.0), (7.4, 7.6), (8.8, 4.8), (10.3, 11.0)])),
                  cx, cy, scale)
    return [glow(fire, flat((255, 120, 30, 150)), 1.8), outline(fire, (70, 18, 6, 230), 0.5),
            fill(fire, linear((cx, cy - 7 * scale), (cx, cy + 7 * scale), [(0, (214, 52, 26)), (0.45, (246, 128, 36)), (1, (255, 206, 80))])),
            fill(heart, linear((cx, cy - 3 * scale), (cx, cy + 6 * scale), [(0, (255, 214, 96)), (1, (255, 250, 214))]))]


def vial_layers(start, end, width=1.75):
    """A glass vial from its bottom at start to its cork at end, half full of glowing green poison."""
    def at(t, off=0.0):
        return (start[0] + (end[0] - start[0]) * t + off, start[1] + (end[1] - start[1]) * t + off)
    glass = lambda u, v: capsule(u, v, at(0.06), at(0.80), width)  # noqa: E731
    liquid = lambda u, v: capsule(u, v, at(0.06), at(0.52), width * 0.69)  # noqa: E731
    shine = lambda u, v: capsule(u, v, at(0.18, -0.43 * width), at(0.62, -0.43 * width), 0.16 * width)  # noqa: E731
    cork = lambda u, v: capsule(u, v, at(0.82), at(0.95), width * 0.71)  # noqa: E731
    return [glow(liquid, flat((80, 255, 110, 120)), 2.2), outline(glass, (14, 40, 26, 240)), fill(glass, flat((210, 245, 225, 90))),
            fill(liquid, linear(at(0), at(0.52), [(0, (40, 170, 60)), (1, (120, 255, 130))])),
            fill(shine, flat((255, 255, 255, 200))), fill(cork, bevel(flat((176, 122, 70)), (90, 56, 30), 0.9, 0.5))]


def wolf_face(u, v):
    # A wolf's face from the front: a broad head, pointed ears, the ruff at its cheeks. duxaUI's howling wolf in
    # profile read as a rabbit, then a llama, drawn this small.
    return min(ellipse_signed(u, v, 8, 8.4, 4.8, 4.2),
               min(polygon_signed(u, v, [(3.6, 7.0), (3.4, 0.8), (7.0, 4.6)]),
                   polygon_signed(u, v, [(12.4, 7.0), (12.6, 0.8), (9.0, 4.6)])) - 0.3,
               polygon_signed(u, v, [(3.2, 8.4), (2.2, 11.2), (4.6, 12.6), (8, 15.4), (11.4, 12.6), (13.8, 11.2), (12.8, 8.4)]) - 0.2)


def wolf_face_layers(cx, cy, scale):
    """A grey wolf's face centered at (cx, cy): pointed ears, yellow eyes, a pale muzzle and a black nose."""
    face = moved(wolf_face, cx, cy, scale)
    inner_ears = moved(lambda u, v: min(polygon_signed(u, v, [(4.4, 6.0), (4.2, 2.6), (6.4, 4.8)]),
                                        polygon_signed(u, v, [(11.6, 6.0), (11.8, 2.6), (9.6, 4.8)])), cx, cy, scale)
    muzzle = moved(lambda u, v: ellipse_signed(u, v, 8, 11.6, 2.4, 2.6), cx, cy, scale)
    eyes = moved(lambda u, v: min(tilted_ellipse(u, v, 5.9, 8.0, 1.05, 0.62, 20), tilted_ellipse(u, v, 10.1, 8.0, 1.05, 0.62, -20)),
                 cx, cy, scale)
    pupils = moved(lambda u, v: min(circle(u, v, 6.0, 8.0, 0.34), circle(u, v, 10.0, 8.0, 0.34)), cx, cy, scale)
    nose = moved(lambda u, v: ellipse_signed(u, v, 8, 10.4, 1.0, 0.7), cx, cy, scale)
    lit, mid, rim = GREY_FUR
    return [outline(face),
            fill(face, bevel(linear((cx, cy - 7 * scale), (cx, cy + 7 * scale), [(0, lit), (1, mid)]), rim, 0.8 * scale, 0.5)),
            fill(inner_ears, flat((90, 60, 60))), fill(muzzle, bevel(flat((244, 240, 232)), (180, 170, 160), 0.6 * scale, 0.5)),
            fill(eyes, flat((250, 200, 60))), fill(pupils, flat((20, 12, 8))), fill(nose, flat((24, 20, 22)))]


def scales(shape):
    """Rows of overlapping rounded scales, 2 across and 1.6 down, as arcs within shape. Only the rows and columns
    round each point are measured, since every arc would slow the build."""
    def arcs(u, v):
        row = round((v - 1.6) / 1.6)
        best = math.inf
        for r in (row - 1, row, row + 1):
            shift = 1.0 if r % 2 else 0.0
            col = round((u - shift) / 2.0)
            for c in (col - 1, col, col + 1):
                best = min(best, arc_distance(u, v, c * 2.0 + shift, 1.6 + r * 1.6, 1.1, 20, 160))
        return max(best - 0.18, shape(u, v))
    return arcs


def divine_aura_picture():
    # 46: a steel shield with a bright white-violet light bursting at its middle.
    return shield_layers(halo=(230, 200, 255, 120)) + burst_layers(8, 7.4, 5.6, (220, 180, 255))


def resist_fire_picture():
    # 52: a steel shield with flames licking up over its lower half.
    return [*shield_layers(halo=(255, 150, 60, 100)), *flame_layers(4.2, 11.0, 0.55), *flame_layers(11.8, 11.2, 0.55),
            *flame_layers(8.0, 12.4, 0.5)]


def burnout_picture():
    # 53: a red-orange shield with a flame painted on it.
    return shield_layers(palette=RED_METAL, halo=(255, 120, 80, 120)) + flame_layers(8.0, 7.4, 0.48)


def resist_cold_picture():
    # 57: a steel shield with a white snowflake over its lower half.
    return shield_layers(halo=(170, 200, 255, 110)) + snowflake_layers(8.4, 11.2, 0.5)


def aura_of_heat_picture():
    # 58: a glassy blue shield, glowing violet, lighter toward its point.
    return shield_layers(palette=GLASS_BLUE, halo=(170, 150, 255, 140)) + [
        fill(lambda u, v: max(SHIELD(u, v), -circle(u, v, 8, 13.5, 6.5) - 2), flat((255, 255, 255, 50)))]


def spirit_of_snow_picture():
    # 60: a steel shield, a wolf's face at its lower left and a snowflake at its lower right.
    return [*shield_layers(small_shield(8.6, 0.8, 8.4), halo=(170, 200, 255, 100), cx=8.6), *wolf_face_layers(4.4, 11.0, 0.5),
            *snowflake_layers(11.6, 11.6, 0.44)]


def resist_poison_picture():
    # 61: a steel shield in a green glow, a vial of poison across it.
    return shield_layers(halo=(90, 255, 120, 110)) + vial_layers((3.4, 14.2), (13.8, 3.0))


def aura_of_purity_picture():
    # 62: a vial of poison at the left, a steel shield at the right.
    return shield_layers(small_shield(10.2, 1.0, 8.4), cx=10.2) + vial_layers((2.0, 14.6), (9.0, 4.8), 1.5)


def vial_and_skull_picture():
    # 63, in no Quarm spell: a vial of poison and a skull.
    return vial_layers((1.8, 13.8), (9.6, 2.6), 1.5) + skull_layers(11.4, 11.0, 1.0)


def talisman_of_shadoo_picture():
    # 64: a wolf's face with a vial of poison.
    return wolf_face_layers(6.6, 8.6, 0.78) + vial_layers((9.0, 14.8), (14.4, 5.4), 1.4)


def resist_disease_picture():
    # 65: a steel shield in a gold glow, a skull at its lower right.
    return shield_layers(small_shield(7.4, 0.8, 9.2), halo=(255, 220, 120, 130), cx=7.4) + skull_layers(11.4, 11.6, 1.05)


def aura_of_antibody_picture():
    # 66: a skull at the lower left, a steel shield at the right.
    return shield_layers(small_shield(10.0, 0.8, 8.8), cx=10.0) + skull_layers(4.6, 11.6, 1.05)


def shield_and_skull_picture():
    # 67, in no Quarm spell: a steel shield with a skull at its lower left.
    return shield_layers(small_shield(9.0, 0.8, 9.2), cx=9.0) + skull_layers(5.2, 11.8, 1.0)


def talisman_of_jasinth_picture():
    # 68: a steel shield, a wolf's face at its lower left and a skull at its lower right.
    return [*shield_layers(small_shield(8.4, 0.6, 8.4), cx=8.4), *wolf_face_layers(4.2, 11.2, 0.48), *skull_layers(11.8, 12.0, 0.95)]


def resist_magic_picture():
    # 69: a steel shield with a violet light bursting over its lower half.
    return shield_layers(halo=(200, 160, 255, 120)) + burst_layers(8, 10.4, 5.0, (190, 130, 255))


def null_aura_picture():
    # 70: a steel shield at the right, a crossed violet sparkle at its top left.
    return shield_layers(small_shield(9.4, 1.6, 9.4), cx=9.4) + sparkle_layers(4.2, 4.4, 4.0, crossed=True, rim=(220, 140, 255))


def rune_picture():
    # 77: a dark round stone with a rune like an elk's antlers on a stave carved into it, glowing faintly. A letter
    # R read as the alphabet, not a rune.
    stone = lambda u, v: tilted_ellipse(u, v, 8, 8.2, 6.6, 5.4, -18)  # noqa: E731
    mark = union(lambda u, v: capsule(u, v, (8, 4.2), (8, 12.4), 0.5), lambda u, v: capsule(u, v, (8, 8.0), (5.0, 4.6), 0.45),
                 lambda u, v: capsule(u, v, (8, 8.0), (11.0, 4.6), 0.45))
    return [glow(stone, flat((150, 200, 255, 100)), 2.4), outline(stone),
            fill(stone, bevel(radial((6, 5.6), 8, [(0, STONE[0]), (1, STONE[1])]), STONE[2], 1.4, 0.6)),
            fill(inside(stone, lambda u, v: mark(u, v) - 0.25), flat((140, 200, 255, 150))), fill(inside(stone, mark), flat((16, 18, 26)))]


def manaskin_picture():
    # 78: a blue steel shield glowing blue, light welling up from its point.
    return shield_layers(palette=BLUE_METAL, halo=(120, 160, 255, 170)) + [
        fill(lambda u, v: max(SHIELD(u, v), circle(u, v, 8, 14, 6.5)), flat((230, 240, 255, 130)))]


def divine_glory_picture():
    # 90: a white crusader's shield with a red cross, a gold rim and a gold boss.
    rim = lambda u, v: abs(SHIELD(u, v) + 0.45) - 0.4  # noqa: E731
    cross = union(lambda u, v: rounded_rect_distance(u, v, 6.8, 1.6, 9.2, 14.2, 0.2),
                  lambda u, v: rounded_rect_distance(u, v, 3.0, 5.0, 13.0, 7.4, 0.2))
    boss = lambda u, v: circle(u, v, 8, 6.2, 1.5)  # noqa: E731
    return [*shield_layers(palette=ENAMEL, halo=(255, 230, 150, 110), heraldry=False),
            fill(inside(SHIELD, cross), flat((200, 30, 40))), fill(inside(SHIELD, rim), flat(GOLD[1])),
            outline(boss, width=0.4), shaded(boss, GOLD, (7, 5), (9, 7), 0.6, 0.5)]


def sentinel_picture():
    # 96: a steel great helm: a domed top, a band at the eyes with two slits either side of a nose guard, a cross of
    # breathing holes each side under it, and rivets. A flat-topped one looked like a can.
    helm = lambda u, v: min(rounded_rect_distance(u, v, 3.2, 5.0, 12.8, 15.0, 1.6), ellipse_signed(u, v, 8, 5.4, 4.8, 4.2))  # noqa: E731
    band = lambda u, v: rounded_rect_distance(u, v, 3.0, 6.4, 13.0, 9.0, 0.5)  # noqa: E731
    slits = union(lambda u, v: rounded_rect_distance(u, v, 3.8, 7.2, 7.2, 8.2, 0.35),
                  lambda u, v: rounded_rect_distance(u, v, 8.8, 7.2, 12.2, 8.2, 0.35))
    guard = lambda u, v: rounded_rect_distance(u, v, 7.3, 6.0, 8.7, 13.4, 0.5)  # noqa: E731
    holes = lambda u, v: min(circle(u, v, x, y, 0.34) for x, y in ((10.2, 10.8), (11.4, 10.8), (10.8, 10.0), (10.8, 11.6),  # noqa: E731
                                                                     (5.8, 10.8), (4.6, 10.8), (5.2, 10.0), (5.2, 11.6)))
    lit, mid, rim = STEEL
    return [glow(helm, flat((210, 180, 255, 110)), 2.4), outline(helm),
            fill(helm, bevel(linear((4, 1), (12, 15), [(0, lit), (0.55, mid), (1, rim)]), rim, 1.4, 0.5)),
            outline(band, (*rim, 220), 0.4), shaded(band, STEEL, (4, 6), (12, 9), 0.6, 0.45), fill(slits, flat((12, 10, 16))),
            outline(guard, (*rim, 220), 0.35), shaded(guard, STEEL, (7, 6), (9, 13), 0.5, 0.45), fill(holes, flat((18, 16, 22))),
            fill(lambda u, v: min(circle(u, v, x, 13.8, 0.4) for x in (4.6, 11.4)), flat((90, 96, 112)))]


def mana_shield_picture():
    # 98: a blue steel shield with a bright blue-white light bursting from it.
    return shield_layers(palette=BLUE_METAL, halo=(140, 180, 255, 150)) + burst_layers(8, 7.6, 6.6, (150, 190, 255))


def plain_shield_picture():
    # 128, in no Quarm spell: a steel shield.
    return shield_layers(halo=(150, 240, 240, 90))


def talisman_of_tnarg_picture():
    # 130: a shaman's talisman: a wooden hoop round a painted hide disc, blue beads and feathers hanging from it.
    hoop = lambda u, v: abs(circle(u, v, 8, 6.4, 4.8)) - 0.6  # noqa: E731
    disc = lambda u, v: circle(u, v, 8, 6.4, 3.6)  # noqa: E731
    mark = lambda u, v: max(disc(u, v), min(abs(circle(u, v, 8, 6.4, 1.6)) - 0.35, capsule(u, v, (8, 3.6), (8, 9.2), 0.3)))  # noqa: E731
    cords = union(*[lambda u, v, x=x: capsule(u, v, (x, 10.6), (x, 12.4), 0.14) for x in (5.4, 8.0, 10.6)])
    layers = [glow(hoop, flat((255, 220, 120, 120)), 2.4), outline(disc),
              fill(disc, bevel(radial((7, 5.4), 4, [(0, (244, 226, 190)), (1, (190, 160, 110))]), (110, 80, 40), 0.8, 0.5)),
              fill(mark, flat((150, 40, 30))), outline(hoop, width=0.5), shaded(hoop, WOOD, (4, 2), (12, 11), 0.5, 0.5),
              fill(cords, flat((60, 36, 20)))]
    for top, tip in (((5.4, 11.8), (4.8, 15.6)), ((8.0, 12.0), (8.0, 15.8)), ((10.6, 11.8), (11.2, 15.6))):
        feather = lambda u, v, top=top, tip=tip: tapered(u, v, top, tip, 0.75, 0.25)  # noqa: E731
        layers += [outline(feather, width=0.4),
                   fill(feather, bevel(linear(top, tip, [(0, (255, 255, 255)), (1, (220, 170, 110))]), (120, 90, 60), 0.5, 0.5))]
    return layers + [fill(lambda u, v: min(circle(u, v, x, 10.9, 0.5) for x in (5.4, 8.0, 10.6)), flat((60, 150, 230)))]


def skin_like_wood_picture():
    # 131: a green shield covered in overlapping scales.
    return shield_layers(palette=GREEN_SCALES, halo=(150, 230, 140, 110), heraldry=False) + [fill(scales(SHIELD), flat((30, 70, 30, 200)))]


def courage_picture():
    # 132: a steel shield with a crossed white-blue sparkle at its lower right.
    return [*shield_layers(small_shield(7.6, 1.0, 9.6), halo=(170, 200, 255, 100), cx=7.6),
            *sparkle_layers(12.0, 11.8, 3.8, crossed=True, rim=(170, 200, 255))]


def shielding_picture():
    # 133: a steel shield with a bright white star at its heart.
    return shield_layers(halo=(170, 210, 255, 130)) + burst_layers(8, 7.0, 6.8, (170, 210, 255), 180)


def elemental_shield_picture():
    # 148: a steel shield, flames at its lower left and a snowflake at its lower right.
    return [*shield_layers(small_shield(8.4, 0.8, 9.0), cx=8.4), *flame_layers(4.2, 10.6, 0.62), *snowflake_layers(11.8, 11.8, 0.45)]


def resistant_skin_picture():
    # 149: a steel shield, a vial of poison across its lower left and a skull at its lower right.
    return [*shield_layers(small_shield(8.4, 0.6, 9.2), halo=(170, 230, 120, 100), cx=8.4), *vial_layers((1.6, 14.6), (7.6, 7.8), 1.35),
            *skull_layers(11.8, 12.0, 0.95)]


def symbol_of_transal_picture():
    # 150: a lavender shield with a dark blue holy symbol painted on it.
    symbol = union(curve((10.6, 3.8), (6.0, 3.0), (6.4, 6.6), 0.8, 0.6), curve((6.4, 6.6), (10.2, 7.4), (9.6, 10.4), 0.7, 0.6),
                   curve((9.6, 10.4), (8.6, 12.2), (5.6, 11.0), 0.6, 0.35))
    return shield_layers(palette=LAVENDER_METAL, halo=(200, 180, 255, 110), heraldry=False) + [
        fill(inside(SHIELD, symbol), linear((6, 3), (10, 12), [(0, (60, 70, 200)), (1, (30, 30, 120))]))]


def holy_armor_picture():
    # 151: a steel breastplate: its shoulders, the neck opening, a ridge down its middle, rivets.
    plate = lambda u, v: max(polygon_signed(u, v, [(2.2, 3.6), (5.2, 1.8), (10.8, 1.8), (13.8, 3.6), (13.4, 8.4), (11.8, 12.4),  # noqa: E731
                                                   (12.2, 14.8), (3.8, 14.8), (4.2, 12.4), (2.6, 8.4)]) - 0.4, -circle(u, v, 8, 1.2, 2.6))
    ridge = lambda u, v: capsule(u, v, (8, 4.0), (8, 14.4), 0.35)  # noqa: E731
    arm_holes = union(lambda u, v: arc_distance(u, v, 1.0, 8.4, 3.2, 290, 70) - 0.3,
                      lambda u, v: arc_distance(u, v, 15.0, 8.4, 3.2, 110, 250) - 0.3)
    rivets = lambda u, v: min(circle(u, v, x, y, 0.4) for x, y in ((5.0, 4.0), (11.0, 4.0), (5.2, 13.6), (10.8, 13.6)))  # noqa: E731
    return [glow(plate, flat((190, 210, 255, 110)), 2.4), outline(plate), shaded(plate, STEEL, (4, 2), (12, 15), 1.3, 0.6),
            fill(inside(plate, ridge), flat((255, 255, 255, 110))), fill(inside(plate, arm_holes), flat((*STEEL[2], 160))),
            fill(rivets, flat((90, 96, 112)))]


def haze_picture():
    # 152: a steel shield with a sword slanting down across its right side.
    return shield_layers(small_shield(7.4, 0.8, 9.8), cx=7.4) + sword_layers((4.8, 4.4), (14.2, 14.6), (200, 240, 240, 80),
                                                                              half=0.8, guard=1.6, grip=1.4)


def shield_of_thorns_picture():
    # 155: the green scaled shield ringed with brown thorns.
    ends = [((8 + 5.6 * math.cos(a), 8.2 + 6.4 * math.sin(a)), (8 + 7.6 * math.cos(a), 8.2 + 8.2 * math.sin(a)))
            for a in (math.radians(360 * k / 14) for k in range(14))]
    thorns = union(*[lambda u, v, base=base, tip=tip: tapered(u, v, base, tip, 0.55, 0.05) for base, tip in ends])
    shield = heater(8, 2.2, 8.8, 12.2)
    return [outline(thorns, width=0.4),
            fill(thorns, bevel(linear((8, 0), (8, 16), [(0, (220, 170, 100)), (1, (140, 90, 40))]), (70, 40, 14), 0.4, 0.5)),
            *shield_layers(shield, GREEN_SCALES, (150, 230, 140, 90), heraldry=False), fill(scales(shield), flat((30, 70, 30, 200)))]


def mark_of_karn_picture():
    # 156: a blue steel shield with a white star bursting from it.
    return shield_layers(palette=BLUE_METAL, halo=(150, 190, 255, 130)) + burst_layers(8, 6.8, 6.4, (180, 210, 255))


def shield_of_fire_picture():
    # 157: a red shield in a ring of fire.
    ends = [((8 + 4.6 * math.cos(a), 8.2 + 5.4 * math.sin(a)), (8 + 7.8 * math.cos(a + 0.18), 8.2 + 8.2 * math.sin(a + 0.18)))
            for a in (math.radians(360 * k / 12 + 8) for k in range(12))]
    corona = union(*[lambda u, v, base=base, tip=tip: tapered(u, v, base, tip, 1.3, 0.1) for base, tip in ends])
    return [glow(corona, flat((255, 140, 40, 160)), 1.8),
            fill(corona, radial((8, 8.2), 8.4, [(0, (255, 240, 170)), (0.6, (255, 170, 50)), (1, (220, 60, 20))])),
            *shield_layers(heater(8, 2.6, 8.4, 11.6), RED_METAL)]


def mark_of_retribution_picture():
    # 158: a rose-red shield with a white star bursting from it.
    return shield_layers(palette=ROSE_METAL, halo=(255, 140, 170, 130)) + burst_layers(8, 7.0, 6.4, (255, 170, 200))


# Batch 4: eyes, sight and travel.

IRISES = {  # (heart, middle, rim) of an eye's iris
    'grey': ((70, 90, 120), (110, 140, 180), (60, 76, 100)),
    'blue': ((70, 110, 200), (120, 160, 240), (40, 60, 140)),
    'green': ((40, 120, 80), (90, 190, 130), (30, 80, 60)),
    'pink': ((160, 30, 110), (240, 90, 190), (110, 20, 80)),
    'purple': ((90, 40, 160), (170, 110, 240), (60, 30, 120)),
    'white': ((255, 255, 255), (240, 240, 250), (200, 200, 220)),
}
TOMB_STONE = ((222, 222, 226), (150, 150, 160), (70, 70, 80))


def eye_layers(cx=8.0, cy=8.0, scale=1.0, iris='grey'):
    """The Invisibility picture's open eye at (cx, cy) and scale, its iris in one of IRISES."""
    heart, middle, edge = IRISES[iris]
    return [outline(moved(almond, cx, cy, scale)),
            fill(moved(almond, cx, cy, scale), linear((cx, cy - 5 * scale), (cx, cy + 5 * scale),
                                                      [(0, (190, 186, 184)), (0.4, (250, 250, 250)), (1, (220, 220, 224))])),
            fill(moved(lambda u, v: max(circle(u, v, 8, 8.2, 2.9), almond(u, v)), cx, cy, scale),
                 radial((cx, cy + 0.2 * scale), 2.9 * scale, [(0, heart), (0.6, middle), (1, edge)])),
            fill(moved(lambda u, v: circle(u, v, 8, 8.2, 1.2), cx, cy, scale), flat((16, 16, 22))),
            fill(moved(lambda u, v: circle(u, v, 9.1, 7.2, 0.7), cx, cy, scale), flat((255, 255, 255, 230))),
            fill(moved(lambda u, v: abs(circle(u, v, 8, 10.42, 7.22)) - 0.55 if v < 8.2 else 1, cx, cy, scale), flat(SKIN_TONES[1])),
            fill(moved(lambda u, v: abs(almond(u, v) + 0.25) - 0.4, cx, cy, scale), flat((*SKIN_TONES[2], 240)))]


def orb_layers(cx, cy, r, rgb=(230, 120, 220)):
    """A glowing orb, white at its heart."""
    orb = lambda u, v: circle(u, v, cx, cy, r)  # noqa: E731
    return [glow(orb, flat((*rgb, 170)), r * 1.2),
            fill(orb, radial((cx - r * 0.2, cy - r * 0.2), r * 1.1, [(0, (255, 255, 255)), (0.5, (255, 214, 250)), (1, rgb)]))]


def see_invisible_picture():
    # 19: the grey eye, a crossed white sparkle at its lower right.
    return eye_layers(7.4, 7.2, 0.95) + sparkle_layers(12.2, 12.0, 3.4, crossed=True, rim=(220, 230, 255))


def blinding_picture():
    # 23: a white eye blazing in a gold burst of light.
    return [*burst_layers(8, 8.2, 7.6, (255, 240, 180), 170), *eye_layers(iris='white'),
            fill(lambda u, v: circle(u, v, 8, 8.2, 1.1), flat((255, 250, 220)))]


def invisible_to_undead_picture():
    # 33: the grey eye, a skull at its lower right.
    return eye_layers(7.0, 6.8, 0.92) + skull_layers(11.6, 11.6, 1.0)


def invisible_to_animals_picture():
    # 34: the grey eye, a wolf's face at its lower right.
    return eye_layers(7.0, 6.8, 0.92) + wolf_face_layers(11.4, 11.4, 0.52)


def bind_sight_picture():
    # 44: two eyes, a small grey one at the top right and a big blue one at the lower left.
    return eye_layers(10.6, 4.2, 0.55) + eye_layers(7.2, 10.2, 0.85, 'blue')


def green_eye_picture():
    # 45 and 73, in no Quarm spell: a green eye.
    return eye_layers(iris='green')


def sense_the_dead_picture():
    # 74: a green eye, a skull at its lower right.
    return eye_layers(7.0, 6.8, 0.92, 'green') + skull_layers(11.6, 11.6, 1.0)


def sense_summoned_picture():
    # 75: a pink eye, a glowing orb at its lower left.
    return eye_layers(8.6, 7.0, 0.92, 'pink') + orb_layers(3.8, 12.0, 2.2)


def sense_animals_picture():
    # 76: a green eye, a wolf's face at its lower left.
    return eye_layers(9.0, 6.8, 0.9, 'green') + wolf_face_layers(4.6, 11.4, 0.52)


def serpent_sight_picture():
    # 86: a pink-irised eye.
    return eye_layers(iris='pink')


def ultravision_picture():
    # 87: a violet-irised eye in a violet glow.
    return [glow(almond, flat((220, 180, 255, 100)), 2.2), *eye_layers(iris='purple')]


def shifting_sight_picture():
    # 93: two green eyes, a small one at the top right and a big one at the lower left.
    return eye_layers(10.6, 4.2, 0.55, 'green') + eye_layers(7.2, 10.2, 0.85, 'green')


def tombstone_layers(cx=8.0, top=1.6, width=8.4, bottom=15.0, tint=TOMB_STONE, halo=None):
    """A tombstone, round-topped, a cross and lines of writing carved in it."""
    half = width / 2
    stone = lambda u, v: min(rounded_rect_distance(u, v, cx - half, top + half, cx + half, bottom, 0.6), circle(u, v, cx, top + half, half))  # noqa: E731
    lines = lambda u, v: min(capsule(u, v, (cx - half * 0.55, y), (cx + half * 0.55, y), 0.22)  # noqa: E731
                             for y in [top + half + k * (bottom - top - half) / 6 for k in (1, 2, 3, 4)])
    cross = union(lambda u, v: capsule(u, v, (cx, top + half * 0.45), (cx, top + half * 1.25), 0.32),
                  lambda u, v: capsule(u, v, (cx - half * 0.3, top + half * 0.7), (cx + half * 0.3, top + half * 0.7), 0.32))
    lit, mid, rim = tint
    return [*([glow(stone, flat(halo), 2.4)] if halo else []), outline(stone),
            fill(stone, bevel(linear((cx - 3, top), (cx + 3, bottom), [(0, lit), (1, mid)]), rim, 1.2, 0.55)),
            fill(inside(stone, lines), flat((*rim, 170))), fill(inside(stone, cross), flat((*rim, 190)))]


def plain_tombstone_picture():
    # 92, in no Quarm spell: a grey tombstone.
    return tombstone_layers(halo=(220, 220, 240, 90))


def feign_death_picture():
    # 94: a pale green-grey tombstone.
    return tombstone_layers(tint=((214, 236, 220), (130, 170, 146), (50, 80, 60)), halo=(160, 255, 190, 100))


def resurrection_picture():
    # 101: a tombstone with a bright light bursting at its side.
    return tombstone_layers(7.0, 1.6, 8.0, halo=(255, 240, 180, 110)) + burst_layers(11.4, 8.4, 5.8, (255, 230, 150), 170)


def sacrifice_picture():
    # 113: a tombstone with a red X beside it.
    x = union(lambda u, v: capsule(u, v, (10.6, 5.8), (14.8, 10.0), 0.7), lambda u, v: capsule(u, v, (14.8, 5.8), (10.6, 10.0), 0.7))
    return [*tombstone_layers(6.6, 1.6, 8.0, halo=(255, 80, 80, 130)), glow(x, flat((255, 60, 60, 170)), 1.6), outline(x, width=0.4),
            fill(x, bevel(flat((240, 40, 50)), (120, 10, 20), 0.5, 0.5))]


def locate_corpse_picture():
    # 97: a tombstone with a blue eye beside it, looking.
    return tombstone_layers(5.8, 1.6, 7.6) + eye_layers(11.6, 7.4, 0.52, 'blue')


def glimpse_picture():
    # 106: a brass spyglass on a wooden three-legged stand, pointing up to the right.
    base, tip = (2.2, 10.8), (14.2, 3.0)

    def at(t):
        return (base[0] + (tip[0] - base[0]) * t, base[1] + (tip[1] - base[1]) * t)
    legs = union(lambda u, v: capsule(u, v, (8.0, 7.6), (4.6, 15.2), 0.4), lambda u, v: capsule(u, v, (8.0, 7.6), (8.4, 15.4), 0.4),
                 lambda u, v: capsule(u, v, (8.0, 7.6), (11.6, 15.0), 0.4))
    layers = [glow(lambda u, v: capsule(u, v, at(0), at(1), 1.4), flat((190, 210, 255, 90)), 2.0),
              outline(legs, width=0.4), shaded(legs, WOOD, (6, 8), (10, 15), 0.5, 0.5)]
    for t0, t1, r in ((0.0, 0.34, 0.95), (0.3, 0.66, 1.2), (0.62, 1.0, 1.45)):  # the tubes, widening to the lens
        tube = lambda u, v, t0=t0, t1=t1, r=r: capsule(u, v, at(t0), at(t1), r)  # noqa: E731
        band = lambda u, v, t1=t1, r=r: capsule(u, v, at(t1 - 0.04), at(t1), r + 0.25)  # noqa: E731
        end = at(t1)
        layers += [outline(tube), shaded(tube, GOLD, at(t0), end, 0.7, 0.5), outline(band, width=0.35),
                   shaded(band, GOLD, (end[0] - 1, end[1] - 1), (end[0] + 1, end[1] + 1), 0.4, 0.6)]
    return layers + [fill(lambda u, v: tilted_ellipse(u, v, *at(1.0), 0.5, 1.3, -33), flat((170, 220, 255)))]


def door_frame(u, v):
    return min(rounded_rect_distance(u, v, 2.8, 6.0, 13.2, 15.4, 0.4), circle(u, v, 8, 6.4, 5.2))


def door_opening(u, v):
    return min(rounded_rect_distance(u, v, 4.4, 6.4, 11.6, 15.4, 0.2), circle(u, v, 8, 6.4, 3.6))


def doorway_layers(light, deep, halo, star=True):
    """An arched stone doorway, its opening full of light from white to deep, a bright four-pointed star in it."""
    frame = lambda u, v: max(door_frame(u, v), -door_opening(u, v))  # noqa: E731
    return [glow(door_opening, flat(halo), 2.6),
            fill(door_opening, radial((8, 9), 7, [(0, (255, 255, 255)), (0.35, light), (1, deep)])),
            outline(frame), fill(frame, bevel(linear((4, 2), (12, 15), [(0, (110, 110, 120)), (1, (46, 46, 54))]), (20, 20, 26), 0.8, 0.5)),
            fill(inside(frame, lambda u, v: abs(door_opening(u, v) - 0.25) - 0.25), flat((*light, 200))),
            *([fill(lambda u, v: polygon_signed(u - 8, v - 9.0, four_point_star(0, 0, 4.8, 0.7)), flat((255, 255, 255, 230)))]
              if star else [])]


def gate_picture():
    # 31: a doorway full of green light.
    return doorway_layers((110, 255, 140), (20, 120, 50), (100, 255, 130, 150))


def shadow_step_picture():
    # 48: a doorway full of white light, in shadow.
    return doorway_layers((230, 230, 240), (90, 90, 110), (220, 220, 240, 110))


def ring_of_karana_picture():
    # 103, the druids' rings: a doorway full of blue light.
    return doorway_layers((130, 180, 255), (30, 60, 180), (110, 160, 255, 150))


def evacuate_picture():
    # 107: a doorway full of red light, a sword across it.
    return (doorway_layers((255, 130, 120), (170, 20, 20), (255, 90, 80, 150), star=False)
            + sword_layers((5.2, 13.2), (12.2, 4.6), half=0.8, guard=1.6, grip=1.3))


def summon_companion_picture():
    # 120: a doorway full of pink light, a glowing orb in it.
    return doorway_layers((255, 170, 240), (150, 40, 150), (120, 255, 150, 130), star=False) + orb_layers(8, 9.4, 2.4)


def translocate_picture():
    # 121: a doorway full of violet light, a hand in it pointing through.
    hand = moved(pointing_hand, 8.4, 10.6, 0.62)
    return doorway_layers((200, 170, 255), (70, 40, 170), (180, 150, 255, 150), star=False) + [outline(hand), skin_fill(hand, (5, 9), (12, 13), 0.7)]


def translocational_anchor_picture():
    # 122: a dark doorway glowing red, a red crossed circle barring it.
    sign = lambda u, v: min(abs(circle(u, v, 8, 9.6, 2.9)) - 0.55,  # noqa: E731
                            max(capsule(u, v, (5.8, 7.4), (10.2, 11.8), 0.55), circle(u, v, 8, 9.6, 2.9)))
    return [*doorway_layers((120, 20, 30), (40, 0, 8), (255, 60, 60, 140), star=False), glow(sign, flat((255, 60, 60, 170)), 1.6),
            fill(sign, bevel(flat((255, 70, 70)), (140, 10, 20), 0.5, 0.5))]


def circle_of_karana_picture():
    # 129, the wizards' circles: a doorway full of violet-white light.
    return doorway_layers((220, 170, 255), (110, 40, 170), (210, 150, 255, 150))


def feather_ends(k):
    # The k-th of a wing's five feathers side by side, sweeping up to the right, the top one longest. Fanned out from
    # one point, they looked like a feather duster.
    base = (2.4 + 0.85 * k, 8.2 + 1.35 * k)
    a = math.radians(-42 + 5 * k)
    reach = 11.8 - 1.7 * k
    return base, (base[0] + reach * math.cos(a), base[1] + reach * math.sin(a)), 1.4 - 0.12 * k, 0.5


def wing_layers(halo):
    """A white bird's wing: five long feathers side by side sweeping up to the right, a rounded shoulder over their roots."""
    shoulder = lambda u, v: tilted_ellipse(u, v, 4.2, 10.4, 2.8, 2.0, -40)  # noqa: E731
    whole = union(shoulder, *[lambda u, v, k=k: tapered(u, v, *feather_ends(k)) for k in range(5)])
    layers = [glow(whole, flat(halo), 2.4)]
    for k in range(4, -1, -1):
        ends = feather_ends(k)
        feather = lambda u, v, ends=ends: tapered(u, v, *ends)  # noqa: E731
        layers += [outline(feather, (40, 50, 70, 220), 0.45), shaded(feather, FEATHER, ends[0], ends[1], 0.7, 0.45)]
    return layers + [outline(shoulder, (40, 50, 70, 220), 0.45), shaded(shoulder, FEATHER, (2, 8), (6, 13), 0.8, 0.45)]


def levitate_picture():
    # 80: a white bird's wing in a pale blue glow.
    return wing_layers((210, 230, 255, 120))


def whirling_wind_picture():
    # 85: the wing in a red glow.
    return wing_layers((255, 140, 140, 140))


def summon_horse_picture():
    # 112: the winged boot with a green sparkle.
    return run_speed_picture() + sparkle_layers(3.2, 3.8, 3.2, rim=(150, 255, 170))


def lung(u, v, side):
    # One lung: tall, rounded at its apex and its outer side, straighter along its inner edge, flattish at its base.
    # Drawn as the left one, mirrored for the right (side -1).
    x = 8 + side * (u - 8)
    return max(min(ellipse_signed(x, v, 5.0, 9.6, 3.2, 5.2), ellipse_signed(x, v, 5.4, 12.0, 3.0, 2.8)), x - 7.1, v - 14.4)


def suffocate_picture():
    # 137: a pair of darkened lungs on their windpipe, in a swirl of violet gas. duxaUI's skull with a wing didn't say
    # it (the user); the user picked this over lungs wound with smoke, draining grey, squeezed by a shadowy hand or
    # crossed out, and over a pale head gasping or strangled.
    lungs = union(lambda u, v: lung(u, v, 1), lambda u, v: lung(u, v, -1))
    pipe = union(lambda u, v: capsule(u, v, (8, 0.8), (8, 5.8), 0.85), lambda u, v: capsule(u, v, (8, 5.6), (5.8, 7.8), 0.55),
                 lambda u, v: capsule(u, v, (8, 5.6), (10.2, 7.8), 0.55))
    rings = lambda u, v: max(min(abs(v - y) - 0.18 for y in (2.2, 3.6, 5.0)), pipe(u, v))  # noqa: E731
    puffs = union(*[lambda u, v, x=x, y=y, r=r: circle(u, v, x, y, r) for x, y, r in
                    ((2.2, 5.0, 1.6), (13.8, 4.6, 1.5), (1.4, 10.4, 1.5), (14.6, 10.0, 1.4), (3.4, 14.6, 1.6), (12.6, 14.8, 1.6), (8.0, 15.2, 1.2))])
    swirl = union(curve((1.0, 7.6), (8.0, 3.0), (15.0, 7.2), 0.4, 0.25), curve((1.4, 12.8), (8.0, 8.6), (14.8, 12.6), 0.4, 0.25))
    return [glow(puffs, flat((190, 110, 255, 150)), 1.8), fill(puffs, radial((8, 9), 9, [(0, (210, 150, 255, 200)), (1, (120, 60, 180, 200))])),
            glow(lungs, flat((190, 110, 255, 140)), 2.2), outline(pipe), fill(pipe, bevel(flat((236, 200, 206)), (120, 70, 80), 0.6, 0.5)),
            fill(rings, flat((150, 100, 110, 200))), outline(lungs),
            fill(lungs, bevel(linear((8, 4), (8, 15), [(0, (200, 150, 190)), (1, (120, 80, 130))]), (60, 30, 70), 1.2, 0.55)),
            fill(swirl, flat((200, 150, 255, 190)))]


def true_north_picture():
    # 79: an open brass pocket compass: its lid behind, a white face with marks and a red needle pointing north.
    lid = lambda u, v: tilted_ellipse(u, v, 9.6, 4.6, 5.4, 3.0, -16)  # noqa: E731
    case = lambda u, v: circle(u, v, 7.4, 9.4, 5.6)  # noqa: E731
    face = lambda u, v: circle(u, v, 7.4, 9.4, 4.3)  # noqa: E731
    marks = lambda u, v: min(capsule(u, v, (7.4 + 3.3 * math.cos(a), 9.4 + 3.3 * math.sin(a)),  # noqa: E731
                                     (7.4 + 4.0 * math.cos(a), 9.4 + 4.0 * math.sin(a)), 0.2) for a in (math.radians(90 * k) for k in range(4)))
    return [glow(case, flat((255, 220, 140, 110)), 2.2), outline(lid), shaded(lid, GOLD, (6, 2), (13, 7), 0.8, 0.55),
            fill(lambda u, v: tilted_ellipse(u, v, 9.6, 4.6, 4.2, 2.1, -16), flat((*GOLD[2], 200))),
            outline(case), shaded(case, GOLD, (3, 5), (11, 14), 0.9, 0.55),
            fill(face, radial((6.4, 8.4), 5, [(0, (255, 252, 240)), (1, (220, 212, 196))])), fill(marks, flat((60, 50, 40))),
            fill(lambda u, v: polygon_signed(u, v, [(7.4, 6.0), (8.2, 9.4), (6.6, 9.4)]), flat((220, 40, 40))),
            fill(lambda u, v: polygon_signed(u, v, [(7.4, 12.8), (8.2, 9.4), (6.6, 9.4)]), flat((60, 60, 70))),
            fill(lambda u, v: circle(u, v, 7.4, 9.4, 0.5), flat(GOLD[1]))]


def shrink_picture():
    # 108: a white ant seen from above: head, thorax and abdomen, six bent legs and its feelers.
    body = union(lambda u, v: ellipse_signed(u, v, 8, 3.8, 1.6, 1.5), lambda u, v: ellipse_signed(u, v, 8, 7.2, 1.2, 1.8),
                 lambda u, v: ellipse_signed(u, v, 8, 11.8, 2.3, 3.0))
    legs = union(*[curve((8 + side * 0.8, a), (8 + side * 3.4, a - 0.6), (8 + side * 5.2, b), 0.32, 0.22)
                   for side in (-1, 1) for a, b in ((6.2, 3.8), (7.2, 8.4), (8.2, 12.8))],
                 curve((7.4, 2.6), (6.0, 0.8), (4.4, 0.8), 0.22, 0.16), curve((8.6, 2.6), (10.0, 0.8), (11.6, 0.8), 0.22, 0.16))
    ant = union(body, legs)
    return [glow(ant, flat((230, 230, 240, 110)), 2.0), outline(ant, width=0.45),
            fill(ant, bevel(linear((6, 1), (10, 15), [(0, (255, 255, 255)), (1, (190, 192, 200))]), (90, 90, 100), 0.6, 0.5))]


# Batch 5: elements, nature, creatures and weapons.

VINE = ((196, 146, 92), (128, 84, 44), (60, 36, 16))
LEAF = ((170, 230, 120), (70, 150, 60), (20, 60, 20))
PARCHMENT = ((252, 240, 206), (216, 190, 140), (120, 90, 50))
BURLAP = ((226, 196, 146), (164, 124, 78), (80, 56, 30))
RUBY = ((255, 170, 180), (210, 24, 56), (100, 0, 20))
WASP = ((255, 214, 90), (224, 140, 20), (110, 60, 0))
DRAGON_SCALES = ((176, 232, 130), (74, 150, 62), (20, 60, 20))
LUTE_WOOD = ((236, 186, 120), (176, 116, 54), (80, 44, 14))
NOTE_INK = (26, 20, 24)
FIRE_STOPS = [(0, (214, 52, 26)), (0.45, (246, 128, 36)), (1, (255, 206, 80))]
BLUE_FIRE_STOPS = [(0, (40, 60, 200)), (0.45, (90, 150, 255)), (1, (200, 240, 255))]


def diagonal_sword_layers(halo=None):
    """A big steel sword swept up to the right across the tile."""
    return sword_layers((4.0, 12.0), (14.8, 1.2), halo, half=1.15, guard=2.5, grip=1.9)


def summon_dagger_picture():
    # 2: a sword swept up to the right, a sparkle at its top right.
    return diagonal_sword_layers((180, 210, 255, 90)) + sparkle_layers(12.6, 3.8, 3.0, rim=(180, 210, 255))


def shroud_of_hate_picture():
    # 3: the sword, a sparkle at its lower right.
    return diagonal_sword_layers((255, 160, 160, 90)) + sparkle_layers(12.4, 12.2, 3.0, rim=(255, 170, 190))


def divine_might_picture():
    # 104: the sword alone.
    return diagonal_sword_layers((180, 210, 255, 100))


def rain_of_blades_picture():
    # 105: the sword alone, in a red glow.
    return diagonal_sword_layers((255, 150, 150, 110))


def jolt_picture():
    # 110: the sword glowing red-hot, a flash along its blade.
    return diagonal_sword_layers((255, 90, 90, 200)) + sparkle_layers(9.8, 6.0, 4.0, rim=(255, 120, 120))


def crossed_swords_layers(halo):
    return (sword_layers((11.6, 11.6), (1.4, 1.4), halo, half=1.0, guard=2.3, grip=1.8)
            + sword_layers((4.4, 11.6), (14.6, 1.4), half=1.0, guard=2.3, grip=1.8))


def frenzy_picture():
    # 49: two swords crossed.
    return crossed_swords_layers((180, 210, 255, 100))


def cripple_picture():
    # 50: two swords crossed, in a red glow.
    return crossed_swords_layers((255, 140, 140, 110))


def notes_layers(x, y, scale=1.0):
    """Two beamed eighth notes, the first one's head at (x, y), dark with a light edge."""
    heads = union(lambda u, v: tilted_ellipse(u, v, x, y, 1.15 * scale, 0.8 * scale, -22),
                  lambda u, v: tilted_ellipse(u, v, x + 3.2 * scale, y - 0.8 * scale, 1.15 * scale, 0.8 * scale, -22))
    stems = union(lambda u, v: capsule(u, v, (x + 0.95 * scale, y - 0.2 * scale), (x + 0.95 * scale, y - 5.2 * scale), 0.24 * scale),
                  lambda u, v: capsule(u, v, (x + 4.15 * scale, y - 1.0 * scale), (x + 4.15 * scale, y - 6.0 * scale), 0.24 * scale))
    beam = lambda u, v: polygon_signed(u, v, [(x + 0.7 * scale, y - 5.4 * scale), (x + 4.4 * scale, y - 6.2 * scale),  # noqa: E731
                                              (x + 4.4 * scale, y - 5.0 * scale), (x + 0.7 * scale, y - 4.2 * scale)])
    shape = union(heads, stems, beam)
    return [outline(shape, (255, 255, 255, 190), 0.4), fill(shape, flat(NOTE_INK))]


def lute_layers(halo):
    """A lute: its round wooden body at the lower left, the neck and pegbox up to the right, the soundhole, strings."""
    body = lambda u, v: tilted_ellipse(u, v, 5.8, 10.4, 4.2, 4.8, 40)  # noqa: E731
    neck = lambda u, v: capsule(u, v, (8.0, 7.8), (13.4, 2.4), 0.85)  # noqa: E731
    pegbox = lambda u, v: capsule(u, v, (13.2, 2.6), (15.0, 3.6), 0.75)  # noqa: E731
    strings = lambda u, v: max(min(segment_distance(u, v, (3.6 + k * 0.5, 13.2 + k * 0.5), (13.2 + k * 0.4, 2.4 + k * 0.4))  # noqa: E731
                                   for k in (0, 1)) - 0.1, -circle(u, v, 3.2, 13.8, 0.5))
    return [glow(body, flat(halo), 2.2), outline(neck), shaded(neck, WOOD, (8, 8), (13, 2), 0.5, 0.5), outline(pegbox),
            shaded(pegbox, WOOD, (13, 2), (15, 4), 0.5, 0.5), outline(body), shaded(body, LUTE_WOOD, (3, 7), (9, 14), 1.2, 0.55),
            fill(lambda u, v: circle(u, v, 5.6, 10.6, 1.25), flat((40, 22, 10))), fill(strings, flat((250, 240, 220, 220)))]


def melody_of_ervaj_picture():
    # 43: a sword, two notes beside it.
    return sword_layers((3.4, 12.8), (12.8, 3.4), (255, 220, 180, 90), half=0.95, guard=2.1, grip=1.6) + notes_layers(9.4, 14.2, 0.9)


def song_of_travel_picture():
    # 116: a lute, a pair of notes at its lower right.
    return lute_layers((200, 210, 255, 110)) + notes_layers(10.2, 14.6, 0.8)


def chords_of_dissonance_picture():
    # 143: the lute in a red glow, a pair of notes at its lower right.
    return lute_layers((255, 140, 140, 120)) + notes_layers(10.2, 14.6, 0.8)


def terror_picture():
    # 28: a fanged skull, its eyes burning red, in a red glow.
    fangs = union(lambda u, v: polygon_signed(u, v, [(5.9, 12.8), (7.3, 12.8), (6.5, 15.6)]),
                  lambda u, v: polygon_signed(u, v, [(8.7, 12.8), (10.1, 12.8), (9.5, 15.6)]))
    eyes = lambda u, v: min(circle(u, v, 6.0, 7.8, 0.7), circle(u, v, 10.0, 7.8, 0.7))  # noqa: E731
    return [glow(lambda u, v: circle(u, v, 8, 8.4, 5.2), flat((255, 60, 60, 150)), 2.6), *skull_layers(8, 8.4, 1.7),
            outline(fangs, width=0.35), fill(fangs, flat((250, 244, 230))), glow(eyes, flat((255, 40, 40, 200)), 1.0),
            fill(eyes, flat((255, 90, 70)))]


def flame_tongue_layers(cx, cy, scale, stops, halo):
    """The fire picture's flame at (cx, cy) and scale in the colors stops, without its heart."""
    fire = moved(flame, cx, cy, scale)
    return [glow(fire, flat(halo), 2.0), outline(fire, (40, 10, 10, 220), 0.5), fill(fire, linear((cx, cy - 7 * scale), (cx, cy + 7 * scale), stops))]


def wreathed(front, stops, halo):
    """front wreathed in flames: a big flame behind it and two smaller tongues licking up in front at its sides. With
    only the big flame behind, it sat on the skull like a hat."""
    return [*flame_tongue_layers(8, 7.2, 1.2, stops, halo), *front,
            *flame_tongue_layers(3.6, 11.4, 0.55, stops, halo), *flame_tongue_layers(12.4, 11.6, 0.55, stops, halo)]


def ignite_bones_picture():
    # 54: a skull wreathed in flames.
    return wreathed(skull_layers(8, 10.4, 1.15), FIRE_STOPS, (255, 120, 30, 160))


def chill_bones_picture():
    # 59: a skull wreathed in blue flames.
    return wreathed(skull_layers(8, 10.4, 1.15), BLUE_FIRE_STOPS, (110, 170, 255, 160))


def malaise_picture():
    # 55: a wolf's face wreathed in flames.
    return wreathed(wolf_face_layers(8, 10.2, 0.62), FIRE_STOPS, (255, 120, 30, 150))


def violet_skull_picture():
    # 71, a test spell: a skull in a violet glow, a crossed sparkle at its top left.
    return [glow(lambda u, v: circle(u, v, 8, 8.8, 5.0), flat((200, 140, 255, 150)), 2.6), *skull_layers(8.4, 9.0, 1.55),
            *sparkle_layers(3.6, 3.6, 3.0, crossed=True, rim=(220, 160, 255))]


def valiant_companion_picture():
    # 146: a pale skull in a cold blue glow.
    return [glow(lambda u, v: circle(u, v, 8, 8.4, 5.2), flat((150, 200, 255, 170)), 3.0), *skull_layers(8, 8.6, 1.7)]


def fear_picture():
    # 154: a skull in a red glow.
    return [glow(lambda u, v: circle(u, v, 8, 8.4, 5.0), flat((255, 50, 50, 160)), 2.8), *skull_layers(8, 8.6, 1.7)]


def panic_the_dead_picture():
    # 164: a blood-red skull, glowing.
    return [glow(lambda u, v: circle(u, v, 8, 8.4, 5.0), flat((255, 80, 80, 150)), 2.6), *skull_layers(8, 8.6, 1.7),
            fill(lambda u, v: min(circle(u, v, 8, 7.4, 5.1), rounded_rect_distance(u, v, 4.9, 9.3, 11.1, 13.9, 1.2)), flat((220, 30, 40, 110)))]


def tashan_picture():
    # 72: a wolf's face with a star at its top right.
    return [glow(lambda u, v: circle(u, v, 7, 9.6, 5), flat((200, 170, 255, 110)), 2.4), *wolf_face_layers(6.8, 9.8, 0.72),
            *sparkle_layers(12.8, 3.2, 3.2, rim=(210, 190, 255))]


def wolf_form_picture():
    # 81: a wolf's face.
    return [glow(lambda u, v: circle(u, v, 8, 8.6, 5.4), flat((170, 240, 150, 110)), 2.4), *wolf_face_layers(8, 8.4, 0.95)]


def strength_of_nature_picture():
    # 123: a wolf's face, three claw marks slashed at its top right (duxaUI's howling wolf, drawn as the face).
    marks = union(*[lambda u, v, k=k: tapered(u, v, (12.0 + k * 1.62, 1.4), (12.0 + (k * 1.8 - 2.4) * 0.9, 6.44), 0.54, 0.1) for k in range(3)])
    return [glow(lambda u, v: circle(u, v, 6.6, 10, 5), flat((170, 240, 150, 110)), 2.4), *wolf_face_layers(6.6, 10.0, 0.74),
            glow(marks, flat((240, 255, 230, 120)), 1.0), fill(marks, flat((240, 255, 230)))]


def feral_spirit_picture():
    # 144: a wolf's face in a violet spirit glow.
    return [glow(lambda u, v: circle(u, v, 8, 8.6, 5.4), flat((200, 150, 255, 170)), 3.0), *wolf_face_layers(8, 8.4, 0.95)]


def panic_animal_picture():
    # 165: a wolf's face with a red sparkle at its top right.
    return wolf_face_layers(6.8, 9.8, 0.72) + sparkle_layers(12.6, 3.4, 3.2, crossed=True, rim=(255, 110, 110))


def vines_layers(halo):
    """A tangle of woody vines with green leaves on them."""
    stems = union(curve((1.2, 12.6), (6.0, 4.0), (11.6, 9.4), 0.9, 0.6), curve((11.6, 9.4), (15.0, 13.0), (12.6, 15.2), 0.6, 0.35),
                  curve((2.8, 3.4), (9.6, 5.6), (7.0, 12.4), 0.85, 0.55), curve((7.0, 12.4), (5.6, 15.0), (3.0, 14.6), 0.55, 0.3),
                  curve((14.6, 3.0), (9.6, 9.8), (4.6, 8.6), 0.8, 0.45), curve((12.4, 4.6), (14.8, 6.8), (15.2, 9.0), 0.4, 0.2))
    layers = [glow(stems, flat(halo), 1.8), outline(stems, width=0.5),
              fill(stems, bevel(linear((2, 2), (14, 14), [(0, VINE[0]), (1, VINE[1])]), VINE[2], 0.6, 0.55))]
    for x, y, a in ((4.4, 6.2, -30), (10.6, 4.8, 20), (13.4, 11.6, -60), (5.6, 13.2, 40), (8.8, 10.0, 80), (2.6, 10.2, -80), (12.8, 7.6, 10)):
        leaf = lambda u, v, x=x, y=y, a=a: tilted_ellipse(u, v, x, y, 1.5, 0.75, a)  # noqa: E731
        rib = lambda u, v, x=x, y=y, a=a, leaf=leaf: max(abs(-(u - x) * math.sin(math.radians(a)) + (v - y) * math.cos(math.radians(a))) - 0.12, leaf(u, v))  # noqa: E731
        layers += [outline(leaf, width=0.4), fill(leaf, bevel(flat(LEAF[0]), LEAF[1], 0.6, 0.6)), fill(rib, flat((*LEAF[2], 180)))]
    return layers


def snare_picture():
    # 5: a tangle of woody vines with green leaves.
    return vines_layers((160, 230, 140, 100))


def grasping_chains_picture():
    # 29: the tangle in a red glow.
    return vines_layers((255, 130, 130, 110))


def vengeance_of_the_glades_picture():
    # 136 and 145: the tangle in a deep red glow.
    return vines_layers((230, 60, 80, 120))


def drop_layers(cx=8.0, cy=8.0, scale=1.0):
    """A glossy blue water drop at (cx, cy) and scale."""
    drop = moved(lambda u, v: min(circle(u, v, 8, 10.4, 4.4), polygon_signed(u, v, [(4.05, 8.6), (8, 0.8), (11.95, 8.6)])), cx, cy, scale)
    shine = moved(lambda u, v: tilted_ellipse(u, v, 6.0, 9.6, 0.8, 1.8, 20), cx, cy, scale)
    return [glow(drop, flat((120, 220, 255, 130)), 2.2), outline(drop, (10, 40, 70, 230)),
            fill(drop, bevel(radial((cx - 1.4 * scale, cy + 1.2 * scale), 6 * scale, [(0, (200, 240, 255)), (0.5, (60, 170, 240)), (1, (20, 90, 180))]),
                             (10, 50, 120), 1.2 * scale, 0.5)),
            fill(shine, flat((255, 255, 255, 190)))]


def enduring_breath_picture():
    # 20: a blue water drop.
    return drop_layers()


def wake_of_karana_picture():
    # 111: the drop with a sparkle at its heart.
    return drop_layers(8, 8.4, 0.92) + sparkle_layers(8.4, 10.2, 3.2, rim=(160, 250, 250))


def clarity_picture():
    # 21: an eight-pointed star of blue-white light.
    shape = star(8, 8, 8, 7.4, 2.6)
    return [glow(shape, flat((130, 170, 255, 170)), 3.0),
            fill(shape, radial((8, 8), 7.4, [(0, (255, 255, 255)), (0.4, (200, 220, 255)), (1, (90, 130, 255))])),
            fill(lambda u, v: circle(u, v, 8, 8, 1.6), flat((255, 255, 255)))]


def chorus_of_clarity_picture():
    # 24: a big white burst of light in a blue glow.
    return burst_layers(8, 8, 7.2, (160, 200, 255), 170)


def flare_picture():
    # 89: an orange burst of light.
    return burst_layers(8, 8, 7.2, (255, 170, 80), 180)


def cannibalize_picture():
    # 115: a teal burst of light.
    return burst_layers(8, 8, 7.0, (120, 240, 230), 170)


def acumen_picture():
    # 138: a pale gold burst of light.
    return burst_layers(8, 8, 7.0, (250, 230, 170), 170)


def black_symbol_picture():
    # 139: a red burst of light.
    return burst_layers(8, 8, 7.0, (255, 80, 90), 180)


def intellectual_advancement_picture():
    # 141: a small blue burst of light.
    return burst_layers(8, 8, 5.4, (140, 170, 255), 150)


def dim_sparkle_picture():
    # 142, in no Quarm spell: a small dim burst of light.
    return burst_layers(8, 8, 4.8, (150, 150, 200), 120)


def glowing_orb_picture():
    # 124, in no Quarm spell: a glowing pink orb.
    return orb_layers(8, 8, 4.2)


def dove_layers(halo):
    """A white dove flying to the right, its wing raised, an olive twig in its beak."""
    body = union(lambda u, v: tilted_ellipse(u, v, 7.4, 9.6, 4.2, 2.1, -18), lambda u, v: circle(u, v, 11.6, 6.6, 1.6),
                 lambda u, v: polygon_signed(u, v, [(4.4, 10.0), (0.8, 13.0), (1.2, 10.6), (0.4, 9.4), (4.0, 9.0)]) - 0.15)
    wing = lambda u, v: polygon_signed(u, v, [(5.6, 8.8), (3.4, 1.6), (5.4, 3.4), (6.6, 0.8), (7.8, 3.4), (9.4, 1.8), (10.0, 5.4), (9.6, 8.6)]) - 0.3  # noqa: E731
    leaves = union(lambda u, v: tilted_ellipse(u, v, 13.4, 8.8, 0.9, 0.45, 60), lambda u, v: tilted_ellipse(u, v, 15.0, 9.8, 0.9, 0.45, -50))
    dove = union(body, wing)
    return [glow(dove, flat(halo), 2.4), outline(dove), shaded(dove, FEATHER, (4, 2), (11, 12), 0.9, 0.45),
            fill(inside(dove, lambda u, v: abs(wing(u, v) + 0.2) - 0.2 if v > 7.6 else 1), flat((150, 160, 180, 200))),
            fill(lambda u, v: circle(u, v, 12.1, 6.2, 0.3), flat((20, 20, 30))),
            fill(lambda u, v: polygon_signed(u, v, [(12.9, 6.2), (14.6, 6.8), (12.9, 7.4)]), flat((240, 170, 60))),
            fill(curve((14.2, 7.0), (15.0, 8.6), (14.2, 10.6), 0.24, 0.18), flat((110, 80, 40))), outline(leaves, width=0.35), fill(leaves, flat(LEAF[1]))]


def benevolence_picture():
    # 22: a white dove with an olive twig in its beak.
    return dove_layers((200, 220, 255, 120))


def pacify_picture():
    # 39: the dove in a warm glow.
    return dove_layers((255, 230, 170, 120))


def wand_layers(rim):
    """A dark red wand with gold ends, a sparkle in rim at its tip."""
    staff = lambda u, v: capsule(u, v, (3.0, 14.0), (12.2, 4.0), 0.6)  # noqa: E731
    foot = lambda u, v: capsule(u, v, (2.6, 14.4), (3.6, 13.3), 0.75)  # noqa: E731
    cap = lambda u, v: capsule(u, v, (11.6, 4.7), (12.6, 3.6), 0.8)  # noqa: E731
    return [outline(staff), shaded(staff, ((180, 60, 60), (110, 20, 30), (50, 0, 10)), (3, 14), (12, 4), 0.5, 0.5),
            outline(foot, width=0.4), shaded(foot, GOLD, (2, 13), (4, 15), 0.5, 0.5), outline(cap, width=0.4), shaded(cap, GOLD, (11, 3), (13, 5), 0.5, 0.5),
            *sparkle_layers(13.2, 2.8, 3.2, rim=rim)]


def bind_affinity_picture():
    # 30: a wand, a blue-white sparkle at its tip.
    return wand_layers((170, 200, 255))


def cancel_magic_picture():
    # 32: the wand, a red sparkle at its tip.
    return wand_layers((255, 120, 130))


def enchant_gold_picture():
    # 83: a gold ingot, a sparkle at its top left.
    top = lambda u, v: polygon_signed(u, v, [(4.6, 6.4), (12.6, 6.4), (14.6, 10.2), (2.6, 10.2)])  # noqa: E731
    front = lambda u, v: polygon_signed(u, v, [(2.6, 10.2), (14.6, 10.2), (14.6, 12.8), (2.6, 12.8)])  # noqa: E731
    bar = union(top, front)
    return [glow(bar, flat((255, 220, 120, 120)), 2.4), outline(bar),
            fill(front, bevel(linear((2, 10), (2, 13), [(0, GOLD[1]), (1, GOLD[2])]), GOLD[2], 0.4, 0.5)),
            fill(top, bevel(linear((4, 6), (12, 10), [(0, (255, 240, 170)), (1, GOLD[0])]), GOLD[1], 0.5, 0.5)),
            *sparkle_layers(4.4, 4.6, 3.0, rim=(255, 230, 150))]


def identify_picture():
    # 84: a parchment scroll with writing on it, rolled at both ends.
    sheet = lambda u, v: rounded_rect_distance(u, v, 3.6, 3.0, 12.4, 13.0, 0.3)  # noqa: E731
    rolls = union(lambda u, v: capsule(u, v, (2.6, 3.0), (13.4, 3.0), 1.4), lambda u, v: capsule(u, v, (2.6, 13.0), (13.4, 13.0), 1.4))
    lines = lambda u, v: max(min(capsule(u, v, (5.0, y), (11.0 - (k % 2) * 1.6, y), 0.24) for k, y in enumerate((5.6, 7.2, 8.8, 10.4))), sheet(u, v))  # noqa: E731
    return [glow(union(sheet, rolls), flat((255, 230, 180, 100)), 2.2), outline(sheet), shaded(sheet, PARCHMENT, (4, 3), (12, 13), 0.8, 0.4),
            fill(lines, flat((90, 60, 30, 220))), outline(rolls), shaded(rolls, PARCHMENT, (3, 2), (13, 14), 0.9, 0.55)]


def imbue_gem_picture():
    # 100, the enchanters' imbued gems: a faceted ruby with a sparkle.
    outer = [(8 + 6.2 * math.cos(math.radians(22.5 + 45 * k)), 8.4 + 5.2 * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]
    inner = [(8 + 3.2 * math.cos(math.radians(22.5 + 45 * k)), 8.0 + 2.4 * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]
    gem = lambda u, v: polygon_signed(u, v, outer)  # noqa: E731
    facets = lambda u, v: max(min(segment_distance(u, v, a, b) for a, b in zip(inner, outer)) - 0.15, gem(u, v))  # noqa: E731
    return [glow(gem, flat((255, 90, 120, 140)), 2.4), outline(gem),
            fill(gem, bevel(radial((6.4, 6.4), 7.5, [(0, RUBY[0]), (0.5, RUBY[1]), (1, RUBY[2])]), RUBY[2], 1.0, 0.5)),
            fill(lambda u, v: polygon_signed(u, v, inner), radial((7.2, 7.2), 3.4, [(0, (255, 210, 220)), (1, (230, 70, 100))])),
            fill(facets, flat((255, 200, 210, 150))), *sparkle_layers(4.6, 5.4, 2.6)]


def familiar_picture():
    # 125: a small green dragon flying to the right, its bat wings spread. With the wings drawn as one with its body,
    # it read as a green blob.
    wing = lambda u, v: polygon_signed(u, v, [(6.2, 9.4), (1.6, 1.6), (3.8, 4.0), (4.8, 0.8), (6.6, 3.8), (8.6, 1.2), (9.0, 4.4), (10.0, 8.6)]) - 0.15  # noqa: E731
    bones = lambda u, v: max(min(segment_distance(u, v, (7.4, 8.8), tip) for tip in ((1.6, 1.6), (4.8, 0.8), (8.6, 1.2))) - 0.22, wing(u, v))  # noqa: E731
    body = union(lambda u, v: tilted_ellipse(u, v, 7.8, 10.2, 3.6, 1.55, -8), curve((10.6, 9.4), (12.6, 9.0), (13.0, 6.8), 1.0, 0.8),
                 lambda u, v: tilted_ellipse(u, v, 13.8, 5.8, 1.9, 0.95, -22), lambda u, v: tapered(u, v, (13.2, 5.0), (12.2, 3.4), 0.38, 0.1),
                 curve((4.6, 10.8), (1.8, 12.2), (1.0, 14.6), 0.8, 0.25), lambda u, v: polygon_signed(u, v, [(0.4, 14.2), (1.8, 14.0), (0.8, 15.6)]),
                 lambda u, v: tapered(u, v, (7.4, 11.4), (6.8, 13.6), 0.5, 0.3), lambda u, v: tapered(u, v, (9.4, 11.2), (9.8, 13.4), 0.5, 0.3))
    lit, mid, rim = DRAGON_SCALES
    return [glow(union(body, wing), flat((180, 240, 150, 110)), 2.0), outline(wing),
            fill(wing, linear((6, 1), (9, 9), [(0, (150, 210, 120, 230)), (1, (70, 130, 60, 230))])), fill(bones, flat((40, 80, 30))),
            outline(body), fill(body, bevel(linear((4, 6), (13, 12), [(0, lit), (1, mid)]), rim, 0.7, 0.5)),
            fill(lambda u, v: circle(u, v, 14.3, 5.5, 0.28), flat((250, 220, 60)))]


def dimensional_pocket_picture():
    # 126: a full burlap sack tied at the neck with a cord, a tuft of cloth above it. A wider tuft read as a crown.
    sack = union(lambda u, v: ellipse_signed(u, v, 8, 10.8, 5.4, 4.4), lambda u, v: polygon_signed(u, v, [(6.6, 7.4), (9.4, 7.4), (9.6, 5.4), (6.4, 5.4)]),
                 lambda u, v: polygon_signed(u, v, [(6.6, 5.6), (5.4, 3.0), (7.0, 3.8), (8.0, 2.6), (9.0, 3.8), (10.6, 3.0), (9.4, 5.6)]) - 0.2)
    cord = union(lambda u, v: capsule(u, v, (6.0, 6.0), (10.0, 6.0), 0.5), curve((9.8, 6.2), (11.2, 7.0), (10.8, 8.8), 0.3, 0.25))
    folds = inside(sack, union(curve((6.6, 7.4), (5.0, 10.0), (4.6, 13.4), 0.18, 0.18), curve((9.4, 7.4), (11.2, 10.4), (11.6, 13.2), 0.18, 0.18)))
    return [glow(sack, flat((255, 220, 170, 90)), 2.2), outline(sack), shaded(sack, BURLAP, (4, 3), (12, 15), 1.1, 0.5),
            fill(folds, flat((*BURLAP[2], 150))), outline(cord, width=0.4), shaded(cord, WOOD, (5, 6), (11, 9), 0.4, 0.5)]


def summon_arrows_picture():
    # 127: a bow drawn with an arrow nocked, pointing up to the left.
    limb = lambda u, v: arc_distance(u, v, 12.0, 12.0, 8.6, 160, 290) - 0.75  # noqa: E731
    ends = [(12.0 + 8.6 * math.cos(math.radians(a)), 12.0 + 8.6 * math.sin(math.radians(a))) for a in (160, 290)]
    shaft = lambda u, v: capsule(u, v, (13.4, 13.4), (3.4, 3.4), 0.32)  # noqa: E731
    head = lambda u, v: polygon_signed(u, v, [(1.4, 1.4), (5.2, 2.6), (2.6, 5.2)])  # noqa: E731
    vanes = union(lambda u, v: polygon_signed(u, v, [(13.8, 13.8), (12.6, 10.8), (11.4, 11.4)]),
                  lambda u, v: polygon_signed(u, v, [(13.8, 13.8), (10.8, 12.6), (11.4, 11.4)]))
    return [glow(limb, flat((190, 240, 160, 100)), 2.0), fill(lambda u, v: segment_distance(u, v, ends[0], ends[1]) - 0.16, flat((240, 236, 220))),
            outline(limb), shaded(limb, WOOD, (4, 4), (14, 14), 0.6, 0.5), outline(shaft, width=0.4), shaded(shaft, WOOD, (4, 4), (13, 13), 0.3, 0.4),
            outline(vanes, width=0.35), fill(vanes, flat((220, 50, 50))), outline(head, width=0.4), shaded(head, STEEL, (1, 1), (5, 5), 0.5, 0.5)]


def drones_of_doom_picture():
    # 159: a wasp from above, its wings spread.
    wings = union(lambda u, v: tilted_ellipse(u, v, 4.4, 5.0, 3.4, 1.4, -28), lambda u, v: tilted_ellipse(u, v, 11.6, 5.0, 3.4, 1.4, 28),
                  lambda u, v: tilted_ellipse(u, v, 5.0, 7.4, 2.4, 1.0, 12), lambda u, v: tilted_ellipse(u, v, 11.0, 7.4, 2.4, 1.0, -12))
    body = union(lambda u, v: circle(u, v, 8, 2.8, 1.35), lambda u, v: ellipse_signed(u, v, 8, 5.6, 1.6, 1.6),
                 lambda u, v: ellipse_signed(u, v, 8, 10.4, 2.3, 3.6), lambda u, v: polygon_signed(u, v, [(7.4, 13.6), (8.6, 13.6), (8, 15.4)]))
    stripes = lambda u, v: max(min(abs(v - y) - 0.45 for y in (8.6, 10.6, 12.6)), body(u, v))  # noqa: E731
    antennae = union(curve((7.4, 1.8), (6.4, 0.6), (5.2, 0.8), 0.18, 0.14), curve((8.6, 1.8), (9.6, 0.6), (10.8, 0.8), 0.18, 0.14))
    return [outline(wings, (40, 50, 70, 180), 0.35), fill(wings, flat((220, 236, 255, 150))), glow(body, flat((255, 220, 100, 110)), 1.8),
            outline(body), fill(body, bevel(linear((7, 2), (9, 14), [(0, WASP[0]), (1, WASP[1])]), WASP[2], 0.8, 0.5)),
            fill(stripes, flat((30, 20, 10))), fill(antennae, flat((30, 20, 10)))]


def creeping_crud_picture():
    # 160: dark ooze oozing down from the top, lumpy, dripping, a drop falling. A straight top band with even drips read
    # as a comb.
    mass = union(*[lambda u, v, x=x, r=r: circle(u, v, x, 1.6, r) for x, r in ((1.2, 2.6), (4.4, 2.8), (7.8, 2.5), (11.2, 2.9), (14.6, 2.6))])
    drips = union(*[lambda u, v, x=x, end=end: min(tapered(u, v, (x, 3.4), (x, end), 1.0, 0.55), circle(u, v, x, end, 0.95))
                    for x, end in ((2.8, 8.6), (6.2, 11.8), (9.6, 7.2), (13.0, 10.4))])
    drop = lambda u, v: min(circle(u, v, 6.2, 14.6, 0.9), polygon_signed(u, v, [(5.4, 14.4), (6.2, 12.8), (7.0, 14.4)]))  # noqa: E731
    ooze = union(mass, drips, drop)
    shine = inside(ooze, lambda u, v: min(capsule(u, v, (x - 0.35, 3.6), (x - 0.35, end - 1.2), 0.16) for x, end in ((2.8, 8.6), (6.2, 11.8), (13.0, 10.4))))
    return [glow(ooze, flat((180, 200, 90, 110)), 2.0), outline(ooze, (10, 12, 4, 240)),
            fill(ooze, bevel(linear((8, 0), (8, 15), [(0, (96, 110, 40)), (1, (40, 46, 16))]), (14, 16, 6), 0.8, 0.5)),
            fill(shine, flat((220, 240, 160, 170)))]


def lightning_bolt_picture():
    # 162: a white-hot lightning bolt in a violet glow.
    bolt = lambda u, v: polygon_signed(u, v, [(10.0, 0.6), (3.8, 8.8), (7.4, 8.8), (4.8, 15.6), (12.4, 6.4), (8.6, 6.4), (11.8, 0.6)]) - 0.15  # noqa: E731
    return [glow(bolt, flat((200, 150, 255, 190)), 2.8), outline(bolt, (40, 10, 80, 230), 0.5),
            fill(bolt, linear((10, 0), (5, 16), [(0, (255, 255, 255)), (0.6, (240, 230, 255)), (1, (200, 170, 255))]))]


SPELL_PICTURES = {
    161: strike_picture, 51: fire_picture, 42: poison_picture, 99: healing_picture, 56: cold_picture,
    41: disease_picture, 1: phantom_armor_picture, 153: banishing_picture, 38: summoned_weapon_picture,
    37: summoned_food_picture, 16: haste_picture, 17: slow_picture, 4: run_speed_picture, 35: mesmerize_picture,
    18: invisibility_picture, 117: root_picture,
    0: rejuvenation_picture, 6: strengthen_picture, 7: weaken_picture, 8: dexterity_picture, 9: agility_picture,
    10: stamina_picture, 11: brilliance_picture, 12: feeblemind_picture, 13: insight_picture, 14: mind_cloud_picture,
    15: charisma_picture, 25: stun_picture, 26: charm_picture, 27: dominate_undead_picture, 36: sathirs_gaze_picture,
    40: mana_sieve_picture, 47: lifetap_picture, 82: mystic_shielding_picture, 88: eye_of_zomm_picture,
    91: animate_dead_picture, 95: voice_graft_picture, 102: call_of_the_hero_picture, 109: summon_corpse_picture,
    114: silence_picture, 118: regeneration_picture, 119: complete_heal_picture, 140: vampiric_embrace_picture,
    163: illusion_picture,
    46: divine_aura_picture, 52: resist_fire_picture, 53: burnout_picture, 57: resist_cold_picture, 58: aura_of_heat_picture,
    60: spirit_of_snow_picture, 61: resist_poison_picture, 62: aura_of_purity_picture, 63: vial_and_skull_picture,
    64: talisman_of_shadoo_picture, 65: resist_disease_picture, 66: aura_of_antibody_picture, 67: shield_and_skull_picture,
    68: talisman_of_jasinth_picture, 69: resist_magic_picture, 70: null_aura_picture, 77: rune_picture, 78: manaskin_picture,
    90: divine_glory_picture, 96: sentinel_picture, 98: mana_shield_picture, 128: plain_shield_picture,
    130: talisman_of_tnarg_picture, 131: skin_like_wood_picture, 132: courage_picture, 133: shielding_picture,
    148: elemental_shield_picture, 149: resistant_skin_picture, 150: symbol_of_transal_picture, 151: holy_armor_picture,
    152: haze_picture, 155: shield_of_thorns_picture, 156: mark_of_karn_picture, 157: shield_of_fire_picture,
    158: mark_of_retribution_picture,
    19: see_invisible_picture, 23: blinding_picture, 33: invisible_to_undead_picture, 34: invisible_to_animals_picture,
    44: bind_sight_picture, 45: green_eye_picture, 73: green_eye_picture, 74: sense_the_dead_picture,
    75: sense_summoned_picture, 76: sense_animals_picture, 86: serpent_sight_picture, 87: ultravision_picture,
    93: shifting_sight_picture, 97: locate_corpse_picture, 106: glimpse_picture, 31: gate_picture, 48: shadow_step_picture,
    103: ring_of_karana_picture, 107: evacuate_picture, 120: summon_companion_picture, 121: translocate_picture,
    122: translocational_anchor_picture, 129: circle_of_karana_picture, 80: levitate_picture, 85: whirling_wind_picture,
    137: suffocate_picture, 112: summon_horse_picture, 79: true_north_picture, 108: shrink_picture,
    92: plain_tombstone_picture, 94: feign_death_picture, 101: resurrection_picture, 113: sacrifice_picture,
    2: summon_dagger_picture, 3: shroud_of_hate_picture, 5: snare_picture, 20: enduring_breath_picture, 21: clarity_picture,
    22: benevolence_picture, 24: chorus_of_clarity_picture, 28: terror_picture, 29: grasping_chains_picture,
    30: bind_affinity_picture, 32: cancel_magic_picture, 39: pacify_picture, 43: melody_of_ervaj_picture, 49: frenzy_picture,
    50: cripple_picture, 54: ignite_bones_picture, 55: malaise_picture, 59: chill_bones_picture, 71: violet_skull_picture,
    72: tashan_picture, 81: wolf_form_picture, 83: enchant_gold_picture, 84: identify_picture, 89: flare_picture,
    100: imbue_gem_picture, 104: divine_might_picture, 105: rain_of_blades_picture, 110: jolt_picture,
    111: wake_of_karana_picture, 115: cannibalize_picture, 116: song_of_travel_picture, 123: strength_of_nature_picture,
    124: glowing_orb_picture, 125: familiar_picture, 126: dimensional_pocket_picture, 127: summon_arrows_picture,
    134: haste_picture, 135: slow_picture, 136: vengeance_of_the_glades_picture, 138: acumen_picture,
    139: black_symbol_picture, 141: intellectual_advancement_picture, 142: dim_sparkle_picture,
    143: chords_of_dissonance_picture, 144: feral_spirit_picture, 145: vengeance_of_the_glades_picture,
    146: valiant_companion_picture, 147: slow_picture, 154: fear_picture, 159: drones_of_doom_picture,
    160: creeping_crud_picture, 162: lightning_bolt_picture, 164: panic_the_dead_picture, 165: panic_animal_picture,
}


@functools.lru_cache(maxsize=None)
def spell_tile(tile, size):
    """A tile's glow at size: its color at each pixel, its body's coverage (the rounded square) and its edge line's."""
    dark, bright, _ = SPELL_TILES[tile]
    margin = SPELL_ICON_MARGIN[size]
    scale = (size - 2 * margin) / ICON_SIZE
    paint = radial((8, 7.5), 12.5, [(0, bright), (0.6, mix(dark, bright, 0.45)), (1, dark)])
    pixels = []
    for py in range(size):
        for px in range(size):
            d = rounded_rect_distance(px + 0.5, py + 0.5, 0.5, 0.5, size - 0.5, size - 0.5, CORNER_RADIUS)
            body = clamp(0.5 - d)
            pixels.append((paint((px + 0.5 - margin) / scale, (py + 0.5 - margin) / scale, 0), body,
                           body - clamp(-0.5 - d)))
    return tuple(pixels)


def spell_icon_art(cell, size):
    """A spell icon at size (BOOK_ICON or GEM_ICON): its tile's glow, its picture's layers kept inside the tile's edge
    line, and the edge over them, every pixel snapped(). Coverage is one sample of each shape's distance per pixel,
    0.5 - d clamped: the selector icons' supersampling would take minutes for every cell at both sizes in stock
    Python."""
    tile = SPELL_TILE[cell]
    edge = opaque(SPELL_TILES[tile][2])
    _REMEMBERED.clear()
    layers = SPELL_PICTURES[cell]() if cell in SPELL_PICTURES else []
    margin = SPELL_ICON_MARGIN[size]
    scale = (size - 2 * margin) / ICON_SIZE
    art = Texture(size, size)
    for i, (color, body, on_edge) in enumerate(spell_tile(tile, size)):
        if not body:
            continue
        py, px = divmod(i, size)
        u, v = (px + 0.5 - margin) / scale, (py + 0.5 - margin) / scale
        within = body - on_edge  # how much of the pixel lies inside the edge line
        for kind, shape, paint, radius in layers:
            d = shape(u, v)
            reach = d * scale
            amount = clamp(0.5 - reach) if kind == 'fill' else 1.0 if reach <= 0 else clamp(1 - d / radius) ** 2
            if amount * within:
                color = over(paint(u, v, d), amount * within, color)
        color = over(edge, on_edge, color)
        art.rows[py][px] = color if body == 1 else over(color, body)
    return snapped_art(art)


def spell_icon_sheets():
    """Every cell's icon laid out as the stock sheets: {texture name: Texture}, left to right and down each sheet."""
    sheets = {}
    for size, names, cells in ((BOOK_ICON, SPELL_ICON_SHEETS, SPELL_ICON_CELLS),
                               (GEM_ICON, GEM_ICON_SHEETS, GEM_ICON_CELLS)):
        across = ICON_SHEET // size
        for name in names:
            sheets[name] = Texture(ICON_SHEET, ICON_SHEET)
        for cell in range(cells):
            sheet, spot = divmod(cell, across * across)
            row, column = divmod(spot, across)
            sheets[names[sheet]].paste(spell_icon_art(cell, size), column * size, row * size)
    return sheets


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


def book_slot_art(state):
    """A spell book slot hovered or pressed, so you see which spell a click takes: a ring BOOK_SLOT_MARGIN wide round
    the icon in the state's BOOK_RING_RGB, its outside rounded like the panel's corners, and clear inside, where the
    icon or the page shows. The client sets the slot's Normal itself (see A_SpellBookSlot); if it sets these too,
    nothing lights."""
    icon = range(BOOK_SLOT_MARGIN, BOOK_SLOT - BOOK_SLOT_MARGIN)

    def on_ring(x, y):
        return (rounded_rect_distance(x, y, 0, 0, BOOK_SLOT, BOOK_SLOT, CORNER_RADIUS) < 0
                and not (int(x) in icon and int(y) in icon))

    art = ink(Texture(BOOK_SLOT, BOOK_SLOT), BOOK_SLOT, BOOK_SLOT, on_ring)
    art.rows = [[(*BOOK_RING_RGB[state], alpha) for *_, alpha in row] for row in art.rows]
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


def book_frames():
    """Each spell's frame's top left in the spell book, inside the window: spells 0 to 7 on the left page and 8 to 15
    on the right, two across by four down in the stock reading order."""
    return [(BOOK_PAGE_XS[n // BOOK_PAGE_SPELLS] + n % BOOK_COLUMNS * BOOK_TILE_WIDTH + BOOK_FRAME_X,
             BOOK_PAGES_TOP + PADDING + n % BOOK_PAGE_SPELLS // BOOK_COLUMNS * BOOK_ROW_HEIGHT)
            for n in range(BOOK_SPELLS)]


def book_spread():
    """The spell book's two pages as one picture (see PARCHMENT_RGB): parchment inside a rounded darker edge, with its
    grain, the shading down to the crease between the pages, and each spell's frame."""
    fill = (*PARCHMENT_RGB, 255)
    pages = panel_texture(BOOK_CONTENT_WIDTH, BOOK_PAGES_HEIGHT, fill, (*BOOK_PAGE_EDGE_RGB, 255))
    crease = BOOK_CREASE_X - BOOK_LEFT
    grain = random.Random(BOOK_GRAIN_SEED)
    darker, lighter = BOOK_GRAIN
    for row in pages.rows:
        for x, pixel in enumerate(row):
            if pixel != fill:
                continue  # the edge and the corners
            if x == crease:
                row[x] = (*BOOK_CREASE_RGB, 255)
                continue
            shade = max(0, 1 - (abs(x - crease) - 1) / BOOK_SHADE_WIDTH) ** 2
            roll = grain.random()
            step = STEP * (-1 if roll < darker else 1 if roll < darker + lighter else 0)
            red, green, blue = (p + (s - p) * shade + step for p, s in zip(PARCHMENT_RGB, BOOK_SPINE_RGB))
            low = green // STEP * STEP  # green between two steps lands on either, as likely as it's near it
            green = low + STEP if grain.random() < (green - low) / STEP else low
            row[x] = (*(min(max(round(c), 0), 255) for c in (red, green, blue)), 255)
    frame = panel_texture(BOOK_FRAME, BOOK_FRAME, (*BOOK_FRAME_RGB, 0), (*BOOK_FRAME_RGB, 255))
    for left, top in book_frames():
        left, top = left - BOOK_LEFT, top - BOOK_PAGES_TOP
        for y, frame_row in enumerate(frame.rows):
            row = pages.rows[top + y]
            row[left:left + BOOK_FRAME] = [over(pixel, 1, under) for pixel, under in zip(frame_row, row[left:])]
    return pages


def book_pieces():
    """For BOOK_TEXTURE: the spell book's page strips in each state (see BOOK_TURN_WIDTH), a chevron centered on each,
    like the Actions window's arrows, named like pieces() for icon_square(), and its pages."""
    return {**{f'TogglePage{way}{state}': toggle_art(icon_coverage(ARROW_ICONS[way]), state, BOOK_TURN_WIDTH,
                                                      BOOK_TURN_HEIGHT)
               for way in ARROW_ICONS for state in ICON_LOOKS},
            'BookSpread': book_spread()}


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
        # The spell book's (see SPELLBOOK_FILE): a spell's slot, clear like a gem's, and its ring under the pointer and
        # while pressed (see book_slot_art()), and the memorizing bar across the pages. The pages are in BOOK_TEXTURE.
        'BookSlot': clear_texture(BOOK_SLOT, BOOK_SLOT),
        **{f'BookSlot{state}': book_slot_art(state) for state in BOOK_RING_RGB},
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
        'InspectTitleBar': title_piece(INSPECT_TITLE_HEIGHT),
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


def build_atlas(named_pieces, width=ATLAS_WIDTH, height=ATLAS_HEIGHT):
    """Packs pieces into one texture, left to right in rows. Returns the texture and each piece's rectangle."""
    atlas = Texture(width, height)
    rects = {}
    x = y = row_height = 0
    for name, piece in named_pieces.items():
        cell = extruded(piece)
        if x + cell.width > width:
            x, y, row_height = 0, y + row_height, 0
        if x + cell.width > width or y + cell.height > height:
            raise BuildError(f'The pieces don\'t fit in a {width}x{height} texture')
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


def grid_animation(name, textures, cell):
    """A grid of cell-square pictures over whole ICON_SHEET textures, one frame each, as the client reads the stock
    A_SpellIcons and A_SpellGems: cell n is the nth left to right and down, running on from one texture to the next."""
    frames = [node('Frames', [node('Texture', texture), point('Location', 0, 0), size(ICON_SHEET, ICON_SHEET),
                              point('Hotspot', 0, 0), node('Duration', 1000)]) for texture in textures]
    return node('Ui2DAnimation', [node('Cycle', False), node('Grid', True), node('Vertical', False),
                                  node('CellHeight', cell), node('CellWidth', cell), *frames], name)


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


def shared_definitions(rects, book_rects):
    """What every TriageUI window uses: the textures, every piece's animation (rects in the atlas, book_rects in
    BOOK_TEXTURE) and the frame template."""
    item_close = {state: f'TUI_ItemClose{BUTTON_ART[state]}' for state in BUTTON_STATES}
    return [
        texture_info(PIECES_TEXTURE, ATLAS_WIDTH, ATLAS_HEIGHT),
        texture_info(BACKGROUND_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        texture_info(PERCENT_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        texture_info(FIELD_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        texture_info(GUTTER_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        texture_info(DIVIDER_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        texture_info(BOOK_TEXTURE, BOOK_TEXTURE_WIDTH, BOOK_TEXTURE_HEIGHT),
        *(texture_info(name, ICON_SHEET, ICON_SHEET) for name in SPELL_ICON_SHEETS + GEM_ICON_SHEETS),
        *(animation(f'TUI_{name}', PIECES_TEXTURE, rect) for name, rect in rects.items()),
        *(animation(f'TUI_{name}', BOOK_TEXTURE, rect) for name, rect in book_rects.items()),
        # Far wider than its texture: the client repeats or stretches it, and only the first % is ever
        # inside the clip.
        animation('TUI_PercentSign', PERCENT_TEXTURE, (0, 0, SHOWN_REACH, PERCENT_GLYPH_HEIGHT)),
        # The stock slot backgrounds the client paints by name, stretched to each slot, redefined (see
        # REPLACED_ANIMATIONS): clear rows an effect slot's size, a harmful one with its red bars (see HELPFUL_RGBA and
        # HARMFUL_RGBA).
        animation('BlueIconBackground', PIECES_TEXTURE, rects['HelpfulRow']),
        animation('RedIconBackground', PIECES_TEXTURE, rects['HarmfulRow']),
        # The spellbook slot's art, which the client names itself (default's is a dark 48px square; poweroftwo's, at its
        # slots' size, is its "blank spot"): clear at a spell's slot, like the slot's own.
        animation('A_SpellBookSlot', PIECES_TEXTURE, rects['BookSlot']),
        # Every spell's icon, which the client names itself, at 40px and at 24px (see SPELL_ICON_SHEETS).
        grid_animation('A_SpellIcons', SPELL_ICON_SHEETS, BOOK_ICON),
        grid_animation('A_SpellGems', GEM_ICON_SHEETS, GEM_ICON),
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
        # The inspect window's: the same with a bar only as tall as the player's name, and no close box of ours (see
        # INSPECT_TITLE_HEIGHT).
        frame_template(INSPECT_TEMPLATE, title='TUI_InspectTitleBar'),
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


def static_text(name, screen_id, rect, align_right=False, align_center=False, rgb=TEXT_RGB, wrap=False):
    """Text the client writes into a StaticText it looks up (the spellbook's names and page numbers), in font 3 and
    rgb, on one line, or wrapping onto more with wrap. Not a label(): SIDL.xml makes StaticText a static piece, which
    never takes a click, and gives it no EQType, AlignLeft or Style_ flags, so it has only what the schema lists."""
    x, y, width, height = rect
    return node('StaticText', [
        node('ScreenID', screen_id),
        node('Font', TEXT_FONT),
        node('RelativePosition', True),
        point('Location', x, y),
        size(width, height),
        node('Text', ''),
        color('TextColor', rgb),
        node('NoWrap', not wrap),
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


def icon_button(name, screen_id, x, y, tooltip, icon, side=TOGGLE_SIZE, height=None):
    """A command's square button (the social page arrows), or one side wide and height tall (the spell book's page
    strips), lit like an open toggle while pressed and dimmed while the client disables it."""
    return icon_square(name, screen_id, x, y, tooltip, icon, side, False, ICON_ART, height)


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


def worn_slots(prefix, first_type, top):
    """The 21 worn slots as the inventory window lays them out (see INV_WORN), the top row at top: InvSlot1 to 21,
    their EQTypes first_type + 1 to 21, each showing its icon while it's empty."""
    return [inv_slot(f'{prefix}{eq_type}', f'InvSlot{eq_type}', first_type + eq_type,
                     (LEFT + half * HOT_PITCH // 2, top + row * HOT_PITCH), f'TUI_HotSlot{icon}')
            for eq_type, icon, half, row in INV_WORN]


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
    """Two parchment pages side by side, each two spells across by four down (the spell's icon in its frame, its name
    under it), the memorizing and scribing bar along the top, Previous and Next down the sides, and the page numbers
    and Done along the bottom (see SPELLBOOK_FILE)."""
    bar_rect = (BOOK_LEFT, BOOK_BAR_TOP, BOOK_CONTENT_WIDTH, TICK_HEIGHT)
    parts = [gauge('TUI_SBW_Memorize', 'SBW_Memorize_Gauge', MEMORIZE_TYPE, bar_rect, 'TUI_MemorizeFill', SPELL_RGB),
             gauge('TUI_SBW_Scribe', 'SBW_Scribe_Gauge', SCRIBE_TYPE, bar_rect, 'TUI_MemorizeFill', SPELL_RGB),
             picture('TUI_SBW_Pages', 'TUI_BookSpread', (BOOK_LEFT, BOOK_PAGES_TOP, BOOK_CONTENT_WIDTH,
                                                          BOOK_PAGES_HEIGHT))]  # the frames drawn on them
    frames = book_frames()
    # Each slot inside its frame, the icon and the ring round it (see BOOK_SLOT_MARGIN): the client puts the spell's
    # icon in the decal and may paint the slot BlueIconBackground or A_SpellBookSlot, both clear, or RedIconBackground,
    # its bars stretched under the icon. Hovered or pressed, the ring lights (see book_slot_art()).
    lit = {'Pressed': 'TUI_BookSlotPressed', 'Flyby': 'TUI_BookSlotFlyby', 'PressedFlyby': 'TUI_BookSlotPressed'}
    parts += [node('Button', [
        node('ScreenID', f'SBW_Spell{n}'),
        node('RelativePosition', True),
        point('Location', x + BOOK_FRAME_LINE, y + BOOK_FRAME_LINE),
        size(BOOK_SLOT, BOOK_SLOT),
        node('Style_Transparent', False),
        node('Style_Checkbox', False),
        node('ButtonDrawTemplate', [node('Normal', 'TUI_BookSlot'), *(node(state, art) for state, art in lit.items()),
                                    node('NormalDecal', BUFF_ICONS)]),
        point('DecalOffset', BOOK_SLOT_MARGIN, BOOK_SLOT_MARGIN),
        node('DecalSize', [node('CX', BOOK_ICON), node('CY', BOOK_ICON)]),
    ], f'TUI_SBW_Spell{n}') for n, (x, y) in enumerate(frames)]
    parts += [static_text(f'TUI_SBW_SpellName{n}', f'SBW_SpellName{n}',
                          (x - BOOK_FRAME_X + PADDING, y + BOOK_NAME_TOP, BOOK_NAME_WIDTH, BOOK_NAME_LINES * TEXT_HEIGHT),
                          align_center=True, rgb=BOOK_INK_RGB, wrap=True)
              for n, (x, y) in enumerate(frames)]
    parts += [icon_button(f'TUI_{screen_id}', screen_id, x, BOOK_BAR_TOP, tooltip, f'Page{icon}', BOOK_TURN_WIDTH,
                          BOOK_TURN_HEIGHT)
              for x, (screen_id, tooltip, icon) in zip(BOOK_TURN_XS, BOOK_ARROWS)]
    number_top = BOOK_BAND_TOP + SOCIAL_PAGE_LABEL_TOP  # the digits' ink centered on the band, as on Done
    parts += [static_text('TUI_SBW_LeftPageNum', 'SBW_LeftPageNum',
                          (BOOK_LEFT, number_top, NUMBER_WIDTH, TEXT_HEIGHT)),
              static_text('TUI_SBW_RightPageNum', 'SBW_RightPageNum',
                          (BOOK_RIGHT - NUMBER_WIDTH, number_top, NUMBER_WIDTH, TEXT_HEIGHT), align_right=True)]
    parts.append(button('TUI_SBW_DoneButton', 'DoneButton', '', BOOK_LEFT + (BOOK_CONTENT_WIDTH - BOOK_DONE_WIDTH) // 2,
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
    parts += worn_slots('TUI_IW_InvSlot', 0, LEFT)
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


def inspect_window():
    """Another player's worn gear where the inventory window has yours, the message they wrote on the chat input's
    strip in the middle, and Done along the bottom; their name on the title bar (see INSPECT_FILE)."""
    parts = worn_slots('TUI_INSW_InvSlot', INSPECT_SLOT_TYPE, INSPECT_DOLL_TOP)
    # The field as the quantity window's: a child window drawing the strip, and the see-through message box on it.
    strip = node('Screen', [
        node('RelativePosition', True),
        point('Location', INSPECT_FIELD_X, INSPECT_FIELD_TOP),
        size(INV_MIDDLE_WIDTH, INV_MIDDLE_HEIGHT),
        node('DrawTemplate', FIELD_TEMPLATE),
        node('Style_Transparent', False),
        node('Style_Border', True),
    ], 'TUI_INSW_Field')
    message = node('Editbox', [
        node('ScreenID', 'INSW_Edit'),
        node('Font', TEXT_FONT),
        node('DrawTemplate', EDIT_TEMPLATE),
        node('RelativePosition', True),
        point('Location', INSPECT_FIELD_X + FIELD_PADDING, INSPECT_FIELD_TOP + INSPECT_TEXT_TOP),
        size(INV_MIDDLE_WIDTH - 2 * FIELD_PADDING, INV_MIDDLE_HEIGHT - INSPECT_TEXT_TOP - FIELD_PADDING),
        node('Style_Border', False),
        node('Style_Transparent', True),
        color('TextColor', TEXT_RGB),
        node('Style_Multiline', True),
    ], 'TUI_INSW_Edit')
    done = button('TUI_INSW_DoneButton', 'DoneButton', '', LEFT, INSPECT_BUTTON_TOP, INV_DOLL_WIDTH,
                  TEXT_BUTTON_HEIGHT, font=ACTION_FONT, text='Done')
    # The game writes the player's name over "Inspect", the stock placeholder, in the window's font.
    return window('InspectWnd', 'Inspect', INSPECT_HEIGHT, [*parts, strip, message, done], tooltip='Inspect',
                  width=INSPECT_WIDTH, template=INSPECT_TEMPLATE, title_bar=True, font=TEXT_FONT)


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
    under the list, and the column beside them: your points, how much of your XP goes to AA, the reuse timer, and Train,
    Hotkey and Done (see AA_FILE). A list's position is from its page's top left, which the tab box
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
    # The column, with no AA XP line (see AA_NUMBERS_TOP). The counts are StaticText and the timer a label, as in the
    # stock window.
    x, right = AA_COLUMN_X, AA_RIGHT
    parts.append(vertical_divider('TUI_AAW_Divider', AA_DIVIDER_X, LEFT, AA_BOTTOM - LEFT))
    parts += [picture(name, 'TUI_InvDivider', (x, top, AA_COLUMN_WIDTH, DIVIDER_HEIGHT))
              for name, top in AA_COLUMN_DIVIDERS]
    value_x = right - AA_VALUE_WIDTH
    for n, (caption_id, caption, value_id) in enumerate(AA_NUMBERS):
        top = AA_NUMBERS_TOP + n * TEXT_HEIGHT
        parts += [
            label(f'TUI_AAW_{caption_id}', None, (x, top, value_x - x, TEXT_HEIGHT), caption, screen_id=caption_id),
            static_text(f'TUI_AAW_{value_id}', value_id, (value_x, top, AA_VALUE_WIDTH, TEXT_HEIGHT), align_right=True,
                        rgb=VALUE_RGB),
        ]
    parts += [
        hidden_gauge('TUI_AAW_ExpGauge', 'ExpGauge', 5),
        label('TUI_AAW_PercentLabel', None, (x, AA_SPLIT_TOP, AA_COLUMN_WIDTH, TEXT_HEIGHT), 'XP to AA',
              screen_id='PercentLabel'),
        icon_button('TUI_AAW_LessExpButton', 'LessExpButton', x, AA_SPLIT_ROW_TOP, None, 'Minus', ARROW_SIZE),
        static_text('TUI_AAW_ExpCount', 'ExpCount',
                    (x + ARROW_SIZE + PADDING, AA_SPLIT_ROW_TOP + SOCIAL_PAGE_LABEL_TOP,
                     AA_COLUMN_WIDTH - 2 * (ARROW_SIZE + PADDING), TEXT_HEIGHT), align_center=True, rgb=VALUE_RGB),
        icon_button('TUI_AAW_MoreExpButton', 'MoreExpButton', right - ARROW_SIZE, AA_SPLIT_ROW_TOP, None, 'Plus',
                    ARROW_SIZE),
        label('TUI_AAW_TimerLabel', None, (x, AA_TIMER_TOP, AA_COLUMN_WIDTH, TEXT_HEIGHT), AA_TIMER_CAPTION),
        label('TUI_AAW_Timer', None, (x, AA_TIMER_TOP + TEXT_HEIGHT, AA_COLUMN_WIDTH, TEXT_HEIGHT), '',
              align_right=True, screen_id='Timer', rgb=VALUE_RGB),
    ]
    parts += [button(f'TUI_AAW_{screen_id}', screen_id, '', x, AA_BUTTONS_TOP + n * (TEXT_BUTTON_HEIGHT + BUTTON_ROW_GAP),
                     AA_COLUMN_WIDTH, TEXT_BUTTON_HEIGHT, font=ACTION_FONT, text=button_name)
              for n, (screen_id, button_name) in enumerate(AA_BUTTONS)]
    return window('AAWindow', 'Alternate Advancement Window', AA_HEIGHT, parts, width=AA_WIDTH, inner=inner)


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
                TRACKING_FILE: tracking_window, AA_FILE: aa_window, FRIENDS_FILE: friends_window,
                INSPECT_FILE: inspect_window}


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
    book_atlas, book_rects = build_atlas(book_pieces(), BOOK_TEXTURE_WIDTH, BOOK_TEXTURE_HEIGHT)
    textures = {
        PIECES_TEXTURE: atlas,
        BOOK_TEXTURE: book_atlas,
        BACKGROUND_TEXTURE: Texture(BACKGROUND_SIZE, BACKGROUND_SIZE, PANEL_RGBA),
        PERCENT_TEXTURE: percent_glyph(),
        FIELD_TEXTURE: Texture(BACKGROUND_SIZE, BACKGROUND_SIZE, FIELD_RGBA),
        GUTTER_TEXTURE: clear_texture(BACKGROUND_SIZE, BACKGROUND_SIZE),
        DIVIDER_TEXTURE: Texture(BACKGROUND_SIZE, BACKGROUND_SIZE, ROW_DIVIDER_RGBA),
        **spell_icon_sheets(),
    }
    # Every pixel on the 16 steps, so the client has nothing to dither (see STEP).
    files = {name: tga_bytes(snapped_art(texture)) for name, texture in textures.items()}
    files[ANIMATIONS_FILE] = with_definitions(base_animations, shared_definitions(rects, book_rects),
                                              stranded).encode('latin-1')
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
