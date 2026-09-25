"""TriageUI: EverQuest windows for Project Quarm in the look of EQ Triage's overlays.

The script builds a skin folder from your own copy of a base skin (duxaUI by default) and puts the
TriageUI windows on top of it, so the rest of your UI stays as it is. It uses only the standard
library, and it never changes the base skin.
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
DEFAULT_EQ_DIR = Path(r'C:\QUARM')
DEFAULT_BASE = 'duxaUI'
# Written into every folder this script builds, so a rebuild only ever replaces its own output.
MARKER_FILE = 'TriageUI.txt'

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
# The casting window's text, apart from the target's: a soft red, '#e88080' (the user's pick; a soft
# green, '#8fd19e', at first).
SPELL_RGB = (232, 128, 128)
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
ATLAS_WIDTH = 256  # room for a bar's full-width track and fill
ATLAS_HEIGHT = 512  # room for every button's art with its label drawn in
BACKGROUND_SIZE = 16

PIECES_TEXTURE = 'triageui_pieces.tga'
BACKGROUND_TEXTURE = 'triageui_bg.tga'
PERCENT_TEXTURE = 'triageui_percent.tga'
FIELD_TEXTURE = 'triageui_field.tga'  # the chat input's strip, darker than the panel
GUTTER_TEXTURE = 'triageui_gutter.tga'  # the scrollbar's track: clear, so only the thumb shows
# The skin's copy of the base's EQUI_Animations.xml carries our shared definitions: the client loads it
# before every window file, so every window can use them.
ANIMATIONS_FILE = 'EQUI_Animations.xml'
GROUP_FILE = 'EQUI_GroupWindow.xml'
TARGET_FILE = 'EQUI_TargetWindow.xml'
CASTING_FILE = 'EQUI_CastingWindow.xml'
CHAT_FILE = 'EQUI_ChatWindow.xml'

# Layout. Positions inside a window are relative to the area inside the frame. EQ's built-in fonts run
# from 0 (small) to 6 (large), with nothing in between; the user likes 3. Button labels are our own
# lettering instead (see LABEL_GLYPHS): 2 looked squished, 3 too big.
TEXT_FONT = 3
WINDOW_WIDTH = 200  # the group and casting windows; the target window is narrower
LEFT = PADDING - BORDER
RIGHT = WINDOW_WIDTH - 2 * BORDER - LEFT
BAR_WIDTH = RIGHT - LEFT
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
# Things shown only with a target are a target health gauge whose fill, this wide, is clipped to the
# thing's spot. The client draws a fill's width times the gauge's value, so any health above 0 shows
# the whole spot, and no target (value 0) shows nothing. duxaUI colors its bars the same way.
SHOWN_REACH = 10000
# "Casting:" and a space in font 3 (Arial at 12 and 13px measured 48 to 52); the spell name follows.
CASTING_PREFIX_WIDTH = 50
CAST_BAR_WIDTH = TARGET_RIGHT - LEFT  # the casting bar, across the whole width (the user's request)
# The group window: each member's line, name and health %, with no bar (the user wanted just the values,
# and a shorter window), then their pet's line straight under it, indented, with a thin bar: the client
# gives no number for a pet's health. Each line stays a full-width gauge, so all of it can be clicked.
GROUP_SIZE = 5
# 20% narrower than the other windows (the user's call).
GROUP_WIDTH = WINDOW_WIDTH * 4 // 5
GROUP_RIGHT = GROUP_WIDTH - 2 * BORDER - LEFT
GROUP_CONTENT_WIDTH = GROUP_RIGHT - LEFT
PET_TOP = TEXT_HEIGHT
PET_INDENT = 12
# The pets' bars end where the members' did, as long as the target window's.
GROUP_BAR_WIDTH = TWIN_BAR_WIDTH
PET_BAR_HEIGHT = 2
# Pets' names in the smaller font 2, on a shorter line, so the window is less tall (the user's call).
PET_FONT = 2
PET_TEXT_HEIGHT = 12
PET_BAR_GAP = 1  # between the pet's name and its bar (the user asked for a pixel more)
PET_HEIGHT = PET_TEXT_HEIGHT + PET_BAR_GAP + PET_BAR_HEIGHT
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
BUTTON_WIDTH = (GROUP_CONTENT_WIDTH - BUTTON_GAP) // 2  # the group window's two buttons, filling its row
# Button labels are drawn into the buttons' art in our own pixel lettering: the client's font 2 looked
# squished, font 3 too big, and a skin can't space a font's letters. Each glyph is 7 rows sitting on the
# last, '#' for ink, 1px strokes; lowercase letters start at row 2. Letters are LETTER_SPACING apart (the
# user asked for more room than the font gave) and each label is centered in its button, its x-height
# on the button's middle.
LETTER_SPACING = 2
LABEL_HEIGHT = 7
LABEL_TOP = (BUTTON_HEIGHT - LABEL_HEIGHT) // 2
LABEL_GLYPHS = {
    'A': ('.###.', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'),
    'B': ('####.', '#...#', '#...#', '####.', '#...#', '#...#', '####.'),
    'D': ('####.', '#...#', '#...#', '#...#', '#...#', '#...#', '####.'),
    'F': ('####', '#...', '#...', '###.', '#...', '#...', '#...'),
    'G': ('.###.', '#...#', '#....', '#.###', '#...#', '#...#', '.###.'),
    'I': ('#', '#', '#', '#', '#', '#', '#'),
    'T': ('#####', '..#..', '..#..', '..#..', '..#..', '..#..', '..#..'),
    'a': ('....', '....', '.##.', '...#', '.###', '#..#', '.###'),
    'b': ('#...', '#...', '###.', '#..#', '#..#', '#..#', '###.'),
    'c': ('...', '...', '.##', '#..', '#..', '#..', '.##'),
    'd': ('...#', '...#', '.###', '#..#', '#..#', '#..#', '.###'),
    'e': ('....', '....', '.##.', '#..#', '####', '#...', '.###'),
    'i': ('#', '.', '#', '#', '#', '#', '#'),
    'k': ('#...', '#...', '#..#', '#.#.', '##..', '#.#.', '#..#'),
    'l': ('#', '#', '#', '#', '#', '#', '#'),
    'm': ('.....', '.....', '####.', '#.#.#', '#.#.#', '#.#.#', '#.#.#'),
    'n': ('....', '....', '###.', '#..#', '#..#', '#..#', '#..#'),
    'o': ('....', '....', '.##.', '#..#', '#..#', '#..#', '.##.'),
    'r': ('...', '...', '#.#', '##.', '#..', '#..', '#..'),
    's': ('....', '....', '.###', '#...', '.##.', '...#', '###.'),
    't': ('.#.', '.#.', '###', '.#.', '.#.', '.#.', '..#'),
    'u': ('....', '....', '#..#', '#..#', '#..#', '#..#', '.###'),
    'v': ('.....', '.....', '#...#', '#...#', '.#.#.', '.#.#.', '..#..'),
    'w': ('.....', '.....', '#...#', '#...#', '#.#.#', '#.#.#', '.#.#.'),
}
LABEL_ALPHA = {'Normal': 255, 'Flyby': 255, 'Pressed': 255, 'Disabled': 119}
# The group window's buttons: (ScreenID, label, column). The client shows Follow and Decline in place of
# Invite and Disband while you have an invitation. duxaUI's LFG button is left out at the user's request.
GROUP_BUTTONS = (('InviteButton', 'Invite', 0), ('FollowButton', 'Follow', 0),
                 ('DisbandButton', 'Disband', 1), ('DeclineButton', 'Decline', 1))
# The pet window: the target window's shape, the pet's name on the first line, the bar and HP % on the
# second, then its commands in three columns of two, each column a pair of related ones stacked so they
# read together (the user's idea): Attack over Back (fight, stop fighting), Guard over Follow (hold a
# spot, stop holding it), Taunt (the user's most-clicked) over Dismiss (the default skin's "Go Away" was
# a bit too wide for the button in game). Columns and pairs are a padding apart, and the window is a
# pixel wider than the target's so the three columns come out even (the user's call) and fill the name
# line exactly. Sit, which nobody uses, is hidden.
PET_WINDOW_FILE = 'EQUI_PetInfoWindow.xml'
PET_COLUMNS = (  # each column top to bottom: (ScreenID, text, tooltip), the tooltips the default skin's
    (('AttackButton', 'Attack', 'Pet Attack'), ('BackButton', 'Back', 'Pet Back Off')),
    (('GuardButton', 'Guard', 'Pet Guard Here'), ('FollowButton', 'Follow', 'Pet Follow Me')),
    (('TauntButton', 'Taunt', 'Pet Taunt'), ('LostButton', 'Dismiss', 'Pet Get Lost')),
)
PET_HIDDEN = ('SitButton',)  # the client looks these up, so they stay in the window, unseen
PET_PAIR_GAP = BUTTON_ROW_GAP  # 2, 3 and 4 looked cramped in game
PET_BUTTON_WIDTH = math.ceil((TARGET_RIGHT - LEFT - (len(PET_COLUMNS) - 1) * BUTTON_GAP) / len(PET_COLUMNS))
PET_WIDTH = 2 * PADDING + len(PET_COLUMNS) * PET_BUTTON_WIDTH + (len(PET_COLUMNS) - 1) * BUTTON_GAP
PET_RIGHT = PET_WIDTH - 2 * BORDER - LEFT
PIW_BAR_WIDTH = health_bar_width(PET_RIGHT)  # a pixel longer than the target's, keeping its gaps
# Measured from the bottom of the health line's ink: the HP number and the drawn %, whose bottom matches
# the digits', hang 3px below the bar, and the user found the buttons too close under them.
PET_BUTTONS_TOP = TARGET_LINE2 + PERCENT_INK_TOP + PERCENT_GLYPH_HEIGHT + BUTTON_ROW_GAP
# Every labeled button in use, by size: each gets its own art, drawn at its own size with its label in it.
BUTTON_LABELS = {
    (BUTTON_WIDTH, BUTTON_HEIGHT): tuple(label for _, label, _ in GROUP_BUTTONS),
    (PET_BUTTON_WIDTH, BUTTON_HEIGHT): tuple(label for column in PET_COLUMNS for _, label, _ in column),
}
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
# The Effects and Songs windows, as EQ Triage's tables: a row per slot, the spell's icon and then its
# name, a 1px divider between rows, compact (the user agreed this exception to the 6px rule). The client
# lays the slot buttons out itself, left to right and a pixel apart, so each is as wide as the window's
# inside (one per row), and the dividers sit in the pixel between. The icon is a padding from the window's
# edges. The client paints each slot with BlueIconBackground (helpful) or RedIconBackground (harmful), by
# name, so the skin redefines those two: clear, and a faint red row. The spellbook, item display and
# combat ability windows use them too and change with them (the user's call).
BUFF_FILE = 'EQUI_BuffWindow.xml'
SONG_FILE = 'EQUI_ShortDurationBuffWindow.xml'
BUFF_ICONS = 'BuffIcons'  # the stock spell icons the client puts on each slot
REPLACED_ANIMATIONS = ('BlueIconBackground', 'RedIconBackground')
ROW_ICON = 16
ROW_ICON_MARGIN = PADDING - BORDER
ROW_HEIGHT = ROW_ICON + 2 * ROW_ICON_MARGIN
ROW_PITCH = ROW_HEIGHT + 1
ROW_WIDTH = WINDOW_WIDTH - 2 * BORDER
# Zeal's Buff Timers draws each effect's time left as a tooltip box pinned to its slot button's top left
# (ui_buff.cpp, BuffWindow_PostDraw), in its largest unit only ("2h", "18m", "45s"). It sat over the
# start of the names in game, so the icon starts TIMER_WIDTH further in than the window's padding: 18px,
# the user's call in game (36, then 24 left too much room before the names), then the name.
TIMER_WIDTH = 18
ROW_ICON_X = LEFT + TIMER_WIDTH  # in the slot button, which starts at the inside's left edge
ROW_NAME_X = ROW_ICON_X + ROW_ICON + PADDING
HARMFUL_RGBA = (255, 68, 68, 34)  # a faint red, on the 16-bit steps
# A helpful effect's row: the panel's color at the lowest alpha step, so it looks like the panel but isn't
# clear, which a button seems to treat as click-through.
HELPFUL_RGBA = (*PANEL_RGBA[:3], STEP)
# The Player window, trimmed to what the user wants, in the layout the user gave: "Health" and its
# "current/max" (label 70) on a line, the HP bar under it as in the group window, the same for
# "Mana" (Zeal's label 80, its numbers green, its bar a soft blue), then the resists as a small
# table, a caption over each number, abbreviated as the user prefers. Each section starts a padding
# under the bar above, measured to the caption's ink. The client looks up its four gauges; stamina and
# pet stay, hidden.
PLAYER_FILE = 'EQUI_PlayerWindow.xml'
# Zeal's server tick (gauge 24) as a thin bar along the top of the window's inside, as long as the
# content (the user wanted it along the top border; in the frame itself it didn't show: the client
# draws nothing outside a window's inside area). Your name's ink a padding under it.
TICK_TYPE = 24
TICK_HEIGHT = 2
TICK_TOP = 0
PLAYER_NAME_TYPE = 1  # your name, the first line (the user's request)
PLAYER_NAME_TOP = TICK_TOP + TICK_HEIGHT + math.ceil(PADDING - PERCENT_INK_TOP - PERCENT_SUBPIXEL)
PLAYER_SECTIONS_TOP = PLAYER_NAME_TOP + TEXT_HEIGHT + PADDING  # the user asked for 6px more under the name
PLAYER_SECTION_PITCH = BAR_TOP + BAR_HEIGHT + math.ceil(PADDING - PERCENT_INK_TOP - PERCENT_SUBPIXEL)
MANA_RGB = (120, 165, 235)  # the mana bar: a soft blue, so mana reads apart from HP (the user's pick)
# The values: the current number, "/" and the max, as separate labels (the current right-aligned against
# the slash, the max left-aligned after it in a spot for 4 digits), and the resists' values, all in the
# game's pure green: the game colors the max HP label (18) itself, green in game whatever the skin sets,
# so the user had every value match it rather than mix greens (a softer green and white were tried).
VALUE_RGB = (0, 255, 0)
PLAYER_NUMBER_WIDTH = 28  # "8888" in font 3 (Arial 12px)
SPACE_WIDTH = 3  # a space in font 3 (Arial 12px)
# The slash (4px) with a space either side, so the numbers read apart (the user's request).
PLAYER_SLASH_WIDTH = 4 + 2 * SPACE_WIDTH
RESISTS = (('DR', 13), ('PR', 12), ('MR', 16), ('FR', 14), ('CR', 15))  # (caption, label EQType)
CAPTION_FONT = 2
CAPTION_HEIGHT = 12
CAPTION_INK_TOP = 2  # font 2's capitals start about this far into their line (Arial 10px)
# The resists a padding further down than the rule's (the user's request).
RESISTS_TOP = PLAYER_SECTIONS_TOP + PLAYER_SECTION_PITCH + BAR_TOP + BAR_HEIGHT + 2 * PADDING - CAPTION_INK_TOP
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
# With no title bar, a chat window moves by its bare background, so the input line stops short of the
# bottom right corner and leaves a grab spot there, under the scrollbar, marked with a small grip of
# six dots (the user's idea: a small square in a corner to grab and drag).
GRIP_WIDTH = SCROLL_WIDTH
GRIP_DOTS = [(x, y) for y in (5, 9, 13) for x in (3, 7)]  # each dot's top left pixel; 2x2, crisp
GRIP_ALPHA = SCROLL_LOOKS['Normal']
# Each dot is its own tiny child window with this template, whose background is the dot's color: one
# child window holding all the dots showed them but took the drag, and a picture alone showed nothing
# (the client ignores a picture's anchors). The grab spot between the dots stays the window's own.
DOT_TEMPLATE = 'WDT_TriageDot'
DOT_TEXTURE = 'triageui_dot.tga'
# The input box has no padding setting, so a strip piece draws the field and the see-through input box
# sits on it, inset FIELD_PADDING each side: the text starts about as far in as it sits from the top.
FIELD_PADDING = 4

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


def chevron(up, alpha):
    """A scrollbar arrow button: a small chevron in the middle of a clear SCROLL_WIDTH-wide piece."""
    middle, rise = SCROLL_BUTTON_HEIGHT / 2, 1.25
    tip, arms = (middle - rise, middle + rise) if up else (middle + rise, middle - rise)
    center = SCROLL_WIDTH / 2
    points = ((center - 2.5, arms), (center, tip), (center + 2.5, arms))

    def inside(x, y):
        return min(segment_distance(x, y, points[0], points[1]),
                   segment_distance(x, y, points[1], points[2])) <= GLYPH_STROKE / 2

    return ink(clear_texture(SCROLL_WIDTH, SCROLL_BUTTON_HEIGHT), SCROLL_WIDTH, SCROLL_BUTTON_HEIGHT, inside, alpha)


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


ICONS = {'Actions': actions_icon, 'Inventory': inventory_icon, 'Options': options_icon,
         'Friends': friends_icon, 'Hotbuttons': hotbuttons_icon, 'Spells': spells_icon, 'Pet': pet_icon,
         'Effects': effects_icon}


def icon_coverage(shape):
    """How much of each pixel of the ICON_SIZE grid shape inks, 0 to 1, rows top first. Only pixels near
    the ink's edge are supersampled."""
    step = 1 / SUPERSAMPLE
    rows = []
    for py in range(ICON_SIZE):
        row = []
        for px in range(ICON_SIZE):
            center = shape(px + 0.5, py + 0.5)
            if abs(center) > 1.5:
                row.append(1.0 if center < 0 else 0.0)
            else:
                row.append(sum(shape(px + (i + 0.5) * step, py + (j + 0.5) * step) < 0
                               for j in range(SUPERSAMPLE) for i in range(SUPERSAMPLE)) / SUPERSAMPLE ** 2)
        rows.append(row)
    return rows


def toggle_art(coverage, state):
    """A selector toggle in one state: a button of TOGGLE_LOOKS' colors with the icon centered on it, every
    pixel snapped()."""
    fill, edge, icon_alpha = TOGGLE_LOOKS[state]
    art = panel_texture(TOGGLE_SIZE, TOGGLE_SIZE, fill, edge)
    inset = (TOGGLE_SIZE - ICON_SIZE) // 2
    for y, row in enumerate(coverage):
        for x, amount in enumerate(row):
            if amount:
                under = art.rows[inset + y][inset + x]
                art.rows[inset + y][inset + x] = over((*ICON_RGB, icon_alpha), amount, under)
    return snapped_art(art)


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
    """A button in one state with its label drawn centered on it, in the style's text color."""
    art = panel_texture(width, height, *button_look(style, state))
    text_width, ink = lettering(label)
    left = (width - text_width) // 2
    color = (*BUTTON_STYLES[style][2], LABEL_ALPHA[state])
    for x, y in ink:
        art.rows[LABEL_TOP + y][left + x] = over(color, 1, art.rows[LABEL_TOP + y][left + x])
    return snapped_art(art)


def harmful_row():
    """A harmful effect's row: a faint red across the row, inset like the dividers."""
    row = Texture(ROW_WIDTH, ROW_HEIGHT, (*HARMFUL_RGBA[:3], 0))
    row.rows = [[HARMFUL_RGBA if LEFT <= x < ROW_WIDTH - LEFT else pixel for x, pixel in enumerate(line)]
                for line in row.rows]
    return row


def pieces():
    """Every piece of art the windows use, by name.

    The client draws a gauge's track and fill at their own size instead of stretching them (Infiniti-Blue
    sizes its A_GaugeFill to each gauge for the same reason), so they are exactly as big as their bar.
    The track is the edge color, like the overlay's border; fills are white for FillTint to color, softened
    to BAR_FILL's alpha except the pets', whose grey is soft already.
    """
    coverages = {name: icon_coverage(shape) for name, shape in ICONS.items()}
    return {
        **frame_pieces(),
        'TwinTrack': Texture(TWIN_BAR_WIDTH, TWIN_BAR_HEIGHT, EDGE_FADED),
        'TwinFill': Texture(TWIN_BAR_WIDTH, TWIN_BAR_HEIGHT, BAR_FILL),
        'CastTrack': Texture(CAST_BAR_WIDTH, TWIN_BAR_HEIGHT, EDGE_FADED),
        'CastFill': Texture(CAST_BAR_WIDTH, TWIN_BAR_HEIGHT, BAR_FILL),
        'PIWTrack': Texture(PIW_BAR_WIDTH, TWIN_BAR_HEIGHT, EDGE_FADED),
        'PIWFill': Texture(PIW_BAR_WIDTH, TWIN_BAR_HEIGHT, BAR_FILL),
        'PetGaugeFill': Texture(GROUP_BAR_WIDTH - PET_INDENT, PET_BAR_HEIGHT, WHITE),
        'PlayerTrack': Texture(BAR_WIDTH, BAR_HEIGHT, EDGE_FADED),
        'PlayerFill': Texture(BAR_WIDTH, BAR_HEIGHT, BAR_FILL),
        'TickTrack': Texture(BAR_WIDTH, TICK_HEIGHT, EDGE_FADED),
        'TickFill': Texture(BAR_WIDTH, TICK_HEIGHT, BAR_FILL),
        **{button_art(width, height, label, state): labeled_button_art(width, height, label, state)
           for (width, height), labels in BUTTON_LABELS.items() for label in labels for state in BUTTON_LOOKS},
        **{f'Scroll{way}{state}': chevron(way == 'Up', alpha)
           for way in ('Up', 'Down') for state, alpha in SCROLL_LOOKS.items()},
        **thumb_pieces(),
        **{f'Toggle{name}{state}': toggle_art(coverage, state)
           for name, coverage in coverages.items() for state in TOGGLE_LOOKS},
        'RowDivider': Texture(BAR_WIDTH, 1, ROW_DIVIDER_RGBA),
        'GroupDivider': Texture(GROUP_CONTENT_WIDTH, 1, ROW_DIVIDER_RGBA),  # the same, the group window's width
        'HelpfulRow': Texture(ROW_WIDTH, ROW_HEIGHT, HELPFUL_RGBA),
        'HarmfulRow': harmful_row(),
        'FieldEdge': Texture(1, 1, EDGE_FADED),
        'Clear': clear_texture(1, 1),
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
    lines = list(XML_HEADER)
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


def frame_template(name=FRAME_TEMPLATE, background=BACKGROUND_TEXTURE, edge=None):
    """The overlay's panel as a window frame, with our slim scrollbar. The horizontal scrollbar and title
    boxes, which no TriageUI window shows, keep the base skin's look. edge, when given, is the animation
    for every side and corner of the border instead of the panel's rounded one."""
    border = {side: edge or f'TUI_Frame{piece}' for side, piece in BORDER_PIECES.items()}
    return node('WindowDrawTemplate', [
        node('Background', background),
        scrollbar(),
        stock_scrollbar('HSBTemplate', 'A_HSBLeft', 'A_HSBRight',
                        [('Right', 'A_HSBThumbRight'), ('Left', 'A_HSBThumbLeft'), ('Middle', 'A_HSBThumbMiddle')]),
        stock_buttons('CloseBox', 'A_CloseBtn'),
        stock_buttons('MinimizeBox', 'A_MinimizeBtn'),
        stock_buttons('TileBox', 'A_TileBtn'),
        node('Border', [node(side, art) for side, art in border.items()] + overlaps()),
        node('Titlebar', [node('Right', 'A_RoundedFrameTitleRight'), node('Left', 'A_RoundedFrameTitleLeft'),
                          node('Middle', 'A_RoundedFrameTitleMiddle')] + overlaps()),
    ], name)


def shared_definitions(rects):
    """What every TriageUI window uses: the textures, every piece's animation and the frame template."""
    return [
        texture_info(PIECES_TEXTURE, ATLAS_WIDTH, ATLAS_HEIGHT),
        texture_info(BACKGROUND_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        texture_info(PERCENT_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        texture_info(FIELD_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        texture_info(GUTTER_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        texture_info(DOT_TEXTURE, BACKGROUND_SIZE, BACKGROUND_SIZE),
        *(animation(f'TUI_{name}', PIECES_TEXTURE, rect) for name, rect in rects.items()),
        # Far wider than its texture: the client repeats or stretches it, and only the first % is ever
        # inside the clip.
        animation('TUI_PercentSign', PERCENT_TEXTURE, (0, 0, SHOWN_REACH, PERCENT_GLYPH_HEIGHT)),
        # The stock slot backgrounds the client paints by name, redefined (see REPLACED_ANIMATIONS).
        # A whole row of the panel's color at the lowest alpha step: a button seems to let clicks through
        # its art's clear pixels, and with a clear (first 1x1, then row-sized) one, effects couldn't be
        # clicked off in game (duxaUI's is an opaque bar).
        animation('BlueIconBackground', PIECES_TEXTURE, rects['HelpfulRow']),
        animation('RedIconBackground', PIECES_TEXTURE, rects['HarmfulRow']),
        frame_template(),
        # The chat input's field: a plain strip darker than the panel, outlined by a 1px line in the
        # window edge's color, a faint light line against both the field and the panel around it.
        frame_template(FIELD_TEMPLATE, FIELD_TEXTURE, edge='TUI_FieldEdge'),
        # The chat window's grip dots, each a tiny child window drawing only this background.
        frame_template(DOT_TEMPLATE, DOT_TEXTURE),
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


def health_readout(item, number_type, gauge_type, top, right, number_id):
    """Health at the right end of a line: the number (label number_type, right-aligned) with a drawn %
    after it, ending at right. The % shows only while gauge_type is above 0, so it hides along with
    whoever the line is about.

    Returns the %'s gauge, defined but not a piece of the window, and the pieces.
    """
    percent_x = right - PERCENT_WIDTH
    percent, percent_clip = shown_with_target(
        f'{item}_HPPercent', 'TUI_PercentSign',
        (percent_x, top + PERCENT_INK_TOP, PERCENT_WIDTH, PERCENT_GLYPH_HEIGHT), eq_type=gauge_type)
    # Blank until the client fills it: a 0 showed in the group window's empty slots.
    number = label(f'{item}_HPLabel', number_type, (percent_x - NUMBER_WIDTH, top, NUMBER_WIDTH, TEXT_HEIGHT), '',
                   align_right=True, screen_id=number_id)
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


def shown_with_target(name, art, rect, eq_type=6):
    """art in rect, shown only while eq_type's gauge is above 0 (see SHOWN_REACH): by default the target's
    health, so only while something is targeted.

    Returns the gauge, which belongs in the window file but isn't one of the window's pieces, and the
    clip, which is.
    """
    x, y, width, height = rect
    hidden = gauge(name, None, eq_type, (0, 0, SHOWN_REACH, height), art, TEXT_RGB)
    return hidden, clip(f'{name}_Clip', rect, [hidden])


def twin_bar(name, screen_id, eq_type):
    """The thin bar on the second line of the target and casting windows, with its track."""
    return gauge(name, screen_id, eq_type, (LEFT, TWIN_BAR_TOP, TWIN_BAR_WIDTH, TWIN_BAR_HEIGHT), 'TUI_TwinFill',
                 TEXT_RGB, track='TUI_TwinTrack')


def button_art(width, height, label, state, style=BUTTON_STYLE):
    """The name of a button's art for one style, size, label and state (art is drawn at its own size, with
    its label in it)."""
    return f'Button{style}{width}x{height}{label}{state}'


def button(name, screen_id, label, x, y, width=BUTTON_WIDTH, height=BUTTON_HEIGHT, tooltip=None):
    """A button whose label is drawn in its art (see LABEL_GLYPHS), so its own text is empty."""
    template = node('ButtonDrawTemplate', [node(state, f'TUI_{button_art(width, height, label, BUTTON_ART[state])}')
                                           for state in BUTTON_STATES])
    children = [node('ScreenID', screen_id)] if screen_id else []
    children += [
        node('RelativePosition', True),
        point('Location', x, y),
        size(width, height),
        node('Style_Transparent', False),
    ]
    if tooltip:
        children.append(node('TooltipReference', tooltip))
    return node('Button', children + [
        node('Style_Checkbox', False),
        node('Text', ''),
        template,
    ], name)


def toggle_button(name, screen_id, x, y, tooltip, icon):
    """A square button that stays pressed while what it opens is open, showing an icon in every state."""
    return node('Button', [
        node('ScreenID', screen_id),
        node('RelativePosition', True),
        point('Location', x, y),
        size(TOGGLE_SIZE, TOGGLE_SIZE),
        node('Style_Transparent', False),
        node('TooltipReference', tooltip),
        node('Style_Checkbox', True),
        node('ButtonDrawTemplate', [node(state, f'TUI_Toggle{icon}{TOGGLE_ART[state]}') for state in BUTTON_STATES]),
    ], name)


def hidden_button(name, screen_id):
    """A button the client looks up when it builds a window (it reports an error if one is missing) but
    the user doesn't want: no size, no text and clear art, so it can't be seen or clicked."""
    return node('Button', [
        node('ScreenID', screen_id),
        node('RelativePosition', True),
        point('Location', 0, 0),
        size(0, 0),
        node('Style_Transparent', True),
        node('Style_Checkbox', False),
        node('Text', ''),
        node('ButtonDrawTemplate', [node(state, 'TUI_Clear') for state in BUTTON_STATES]),
    ], name)


def window(item, title, height, parts, tooltip=None, width=WINDOW_WIDTH, inner=(), sizable=False):
    """A window without a title bar, like the overlays with their header hidden, holding parts in drawing order.

    title None leaves the window's name to the client, as for chat windows. inner are defined first but
    aren't pieces of the window: they belong to clips among the parts.
    """
    children = [
        node('ScreenID'),
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
        node('DrawTemplate', FRAME_TEMPLATE),
        node('Style_Titlebar', False),
        node('Style_Closebox', False),
        node('Style_Minimizebox', False),
        node('Style_Border', True),
        node('Style_Sizable', sizable),
    ]
    return list(inner) + parts + [node('Screen', children + [node('Pieces', part[2]) for part in parts], item)]


def stretched(tag, name, screen_id, template, offsets, top_from_bottom, extra):
    """A control that stretches with a resizable window. offsets are (left, top, right, bottom) in from
    the window's inner edges; top_from_bottom measures the top edge up from the bottom instead."""
    left, top, right, bottom = offsets
    return node(tag, [
        node('ScreenID', screen_id),
        node('DrawTemplate', template),
        node('RelativePosition', True),
        node('AutoStretch', True),
        node('LeftAnchorOffset', left),
        node('TopAnchorOffset', top),
        node('RightAnchorOffset', right),
        node('BottomAnchorOffset', bottom),
        node('TopAnchorToTop', not top_from_bottom),
        node('RightAnchorToLeft', False),
        node('BottomAnchorToTop', False),
    ] + extra, name)


# The windows

def target_window():
    """The target's name across the first line; a thin HP bar, then the HP %, on the second."""
    # Zeal blanks the number without a target, and the drawn % hides with it.
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
    # without one) and its bar starts where the target's does, a pixel longer like the window.
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
    """Each member as a line, name and health %, with their pet on its own indented line below.

    Clicking a gauge targets whoever it shows, so each member and pet is one full-row gauge showing the
    name as its own text: pets are as easy to click as players, instead of a 2px bar.
    """
    dividers, gauges, labels, inner = [], [], [], []
    for n in range(1, GROUP_SIZE + 1):
        top = (n - 1) * MEMBER_PITCH
        if n > 1:
            dividers.append(picture(f'TUI_GW_Divider{n}', 'TUI_GroupDivider',
                                    (LEFT, top - DIVIDER_TO_NAME - DIVIDER_HEIGHT, GROUP_CONTENT_WIDTH, DIVIDER_HEIGHT)))
        # No bar, only the name (the gauge's own text): its fill is a clear pixel.
        gauges.append(gauge(f'TUI_GW_Gauge{n}', f'Gauge{n}', 10 + n, (LEFT, top, GROUP_CONTENT_WIDTH, TEXT_HEIGHT), 'TUI_Clear',
                            TEXT_RGB, text_at=(0, 0)))
        gauges.append(gauge(f'TUI_GW_PetGauge{n}', f'PetGauge{n}', 16 + n, (LEFT, top + PET_TOP, GROUP_CONTENT_WIDTH, PET_HEIGHT),
                            'TUI_PetGaugeFill', PET_RGB, text_rgb=PET_RGB, text_at=(PET_INDENT, 0),
                            bar_at=(PET_INDENT, PET_TEXT_HEIGHT + PET_BAR_GAP), font=PET_FONT))
        # "72%" ending at the row's padding; the % shows only while the slot has a member. The client
        # writes a 0 into an empty slot's number, which a skin can't hide (see CLAUDE.md).
        percent, readout = health_readout(f'TUI_GW{n}', 34 + n, 10 + n, top, GROUP_RIGHT, f'HPLabel{n}')
        inner.append(percent)
        labels += readout
    buttons_top = (GROUP_SIZE - 1) * MEMBER_PITCH + MEMBER_HEIGHT + BUTTON_ROW_GAP
    buttons = [button(f'TUI_GW_{screen_id}', screen_id, label, LEFT + column * (BUTTON_WIDTH + BUTTON_GAP), buttons_top)
               for screen_id, label, column in GROUP_BUTTONS]
    height = 2 * BORDER + buttons_top + BUTTON_HEIGHT + BOTTOM_GAP
    return window('GroupWindow', 'Group', height, dividers + gauges + labels + buttons, inner=inner,
                  width=GROUP_WIDTH)


def casting_window():
    """'Casting:' and the spell you're casting (Zeal's label 134), above a bar that fills as the cast
    completes. The target window's size, the bar at the height of its health bar but across the whole
    width between the paddings (the user's request)."""
    spell_x = LEFT + CASTING_PREFIX_WIDTH
    return window('CastingWindow', 'Casting Time', TARGET_HEIGHT, [
        label('TUI_Casting_Prefix', None, (LEFT, 0, CASTING_PREFIX_WIDTH, TEXT_HEIGHT), 'Casting:', rgb=SPELL_RGB),
        # Zeal leaves label 134's color to the skin, so ours holds in game.
        label('TUI_Casting_Spell', 134, (spell_x, 0, TARGET_RIGHT - spell_x, TEXT_HEIGHT), '',
              screen_id='Casting_Spell', rgb=SPELL_RGB),
        gauge('TUI_Casting_Gauge', 'Gauge', 7, (LEFT, TWIN_BAR_TOP, CAST_BAR_WIDTH, TWIN_BAR_HEIGHT), 'TUI_CastFill',
              TEXT_RGB, track='TUI_CastTrack'),
    ], width=TARGET_WIDTH)


def chat_window():
    """Every chat window: no title bar, the chat straight on the panel with a slim scrollbar, the input
    line on a plain strip along the bottom, and a grab spot in the bottom right corner to move the
    window by. All of it follows the window as it's resized."""
    output = stretched('STMLbox', 'TUI_CW_ChatOutput', 'CWChatOutput', FRAME_TEMPLATE,
                       (LEFT, LEFT, LEFT, LEFT + INPUT_HEIGHT + INPUT_GAP), False,
                       # Transparent: the text sits on the window's own panel, with no second one behind it.
                       [node('Style_VScroll', True), node('Style_Border', False), node('Style_Transparent', True)])
    # The field's strip, stopping short of the grab spot: a child window drawing its background and a
    # 1px outline (the user wanted a border with slight contrast to the colors on either side of it).
    strip_left, strip_right = LEFT, LEFT + GRIP_WIDTH + INPUT_GAP
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
    # The input box on the strip, inset FIELD_PADDING each side, see-through so the strip shows.
    field = stretched('Editbox', 'TUI_CW_ChatInput', 'CWChatInput', FIELD_TEMPLATE,
                      (strip_left + FIELD_PADDING, LEFT + INPUT_HEIGHT, strip_right + FIELD_PADDING, LEFT), True,
                      [node('Style_Border', False), node('Style_Transparent', True)])
    # The grab spot in the bottom right corner, GRIP_WIDTH x INPUT_HEIGHT, is the window's own background,
    # so a drag there moves the window. Its dots are six tiny child windows (see DOT_TEMPLATE), each
    # anchored by its edges' distance in from the window's right and bottom, so they stay in the corner.
    dots = []
    for n, (dx, dy) in enumerate(GRIP_DOTS):
        from_right = LEFT + GRIP_WIDTH - dx
        from_bottom = LEFT + INPUT_HEIGHT - dy
        dots.append(node('Screen', [
            node('RelativePosition', True),
            node('AutoStretch', True),
            node('LeftAnchorOffset', from_right),
            node('TopAnchorOffset', from_bottom),
            node('RightAnchorOffset', from_right - 2),
            node('BottomAnchorOffset', from_bottom - 2),
            node('LeftAnchorToLeft', False),
            node('TopAnchorToTop', False),
            node('RightAnchorToLeft', False),
            node('BottomAnchorToTop', False),
            node('DrawTemplate', DOT_TEMPLATE),
            node('Style_Transparent', False),
            node('Style_Border', False),
        ], f'TUI_CW_GripDot{n}'))
    width, height = CHAT_SIZE
    return window('ChatWindow', None, height, [output, strip, field, *dots], width=width, sizable=True)


def selector_window():
    """The buttons that open and close the other windows: one row of icon toggles."""
    toggles = [toggle_button(f'TUI_{screen_id}', screen_id, LEFT + i * (TOGGLE_SIZE + BUTTON_GAP), LEFT, tooltip, icon)
               for i, (screen_id, tooltip, icon) in enumerate(SELECTOR_BUTTONS)]
    toggles += [hidden_button(f'TUI_{screen_id}', screen_id) for screen_id in SELECTOR_HIDDEN]
    return window('SelectorWindow', 'Window Selector', SELECTOR_HEIGHT, toggles, width=SELECTOR_WIDTH)


def picture(name, animation_name, rect):
    """A still picture: not a control, so it never takes a click."""
    x, y, width, height = rect
    return node('StaticAnimation', [
        node('RelativePosition', True),
        point('Location', x, y),
        size(width, height),
        node('Animation', animation_name),
    ], name)


def effects_table(item, title, slots, first_name_type, prefix):
    """A table of effect slots, one row each: the client's slot button (ScreenID BuffN) as wide as the
    row, Zeal's time left at its start, then the spell's icon and the spell's name (label
    first_name_type + N), rows ROW_PITCH apart with a divider between."""
    dividers, buttons, names = [], [], []
    for n in range(slots):
        top = n * ROW_PITCH
        if n:
            dividers.append(picture(f'{prefix}_Divider{n}', 'TUI_RowDivider', (LEFT, top - 1, BAR_WIDTH, 1)))
        buttons.append(node('Button', [
            node('ScreenID', f'Buff{n}'),
            node('RelativePosition', True),
            point('Location', 0, top),
            size(ROW_WIDTH, ROW_HEIGHT),
            node('Style_Transparent', False),
            node('Style_Checkbox', False),
            # The client paints Blue- or RedIconBackground and the spell's icon at runtime.
            node('ButtonDrawTemplate', [node('Normal', REPLACED_ANIMATIONS[0]), node('NormalDecal', BUFF_ICONS)]),
            point('DecalOffset', ROW_ICON_X, ROW_ICON_MARGIN),
            node('DecalSize', [node('CX', ROW_ICON), node('CY', ROW_ICON)]),
        ], f'{prefix}_Buff{n}_Button'))
        names.append(label(f'{prefix}_Buff{n}_Name', first_name_type + n,
                           (ROW_NAME_X, top + (ROW_HEIGHT - TEXT_HEIGHT) // 2, RIGHT - ROW_NAME_X, TEXT_HEIGHT),
                           '', screen_id=f'Buff{n}Label'))
    height = 2 * BORDER + slots * ROW_PITCH - 1
    # The buttons go on top, so a click anywhere on a row reaches its slot and clicks the effect off (the
    # user couldn't with the names over them). Their art is clear, or a faint red, so the names show.
    return window(item, title, height, dividers + names + buttons)


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


def player_window():
    """Your name, then Health and Mana, each a line with its "current/max" and a bar under it, and the
    resists under them as a small table."""
    parts = [label('TUI_PW_Name', PLAYER_NAME_TYPE, (LEFT, PLAYER_NAME_TOP, BAR_WIDTH, TEXT_HEIGHT), '')]
    max_x = RIGHT - PLAYER_NUMBER_WIDTH
    slash_x = max_x - PLAYER_SLASH_WIDTH
    current_x = slash_x - PLAYER_NUMBER_WIDTH
    # (gauge ScreenID, gauge EQType, caption, current and max label EQTypes, bar tint): Zeal gives mana's.
    for n, (screen_id, eq_type, caption, current_type, max_type, tint) in enumerate((
            ('PlayerHP', 1, 'Health', 17, 18, TEXT_RGB),
            ('PlayerMana', 2, 'Mana', 124, 125, MANA_RGB))):
        top = PLAYER_SECTIONS_TOP + n * PLAYER_SECTION_PITCH
        parts += [
            label(f'TUI_PW_{screen_id}Caption', None, (LEFT, top, current_x - LEFT, TEXT_HEIGHT), caption, rgb=PET_RGB),
            label(f'TUI_PW_{screen_id}Current', current_type, (current_x, top, PLAYER_NUMBER_WIDTH, TEXT_HEIGHT), '',
                  align_right=True, rgb=VALUE_RGB),
            label(f'TUI_PW_{screen_id}Slash', None, (slash_x, top, PLAYER_SLASH_WIDTH, TEXT_HEIGHT), '/',
                  align_center=True, rgb=VALUE_RGB),
            label(f'TUI_PW_{screen_id}Max', max_type, (max_x, top, PLAYER_NUMBER_WIDTH, TEXT_HEIGHT), '', rgb=VALUE_RGB),
            gauge(f'TUI_PW_{screen_id}', screen_id, eq_type, (LEFT, top + BAR_TOP, BAR_WIDTH, BAR_HEIGHT),
                  'TUI_PlayerFill', tint, track='TUI_PlayerTrack'),
        ]
    for c, (caption, eq_type) in enumerate(RESISTS):
        x = LEFT + c * BAR_WIDTH // len(RESISTS)
        width = LEFT + (c + 1) * BAR_WIDTH // len(RESISTS) - x
        parts.append(label(f'TUI_PW_{caption}Caption', None, (x, RESISTS_TOP, width, CAPTION_HEIGHT), caption,
                           rgb=PET_RGB, font=CAPTION_FONT, align_center=True))
        parts.append(label(f'TUI_PW_{caption}', eq_type, (x, RESISTS_TOP + CAPTION_HEIGHT, width, TEXT_HEIGHT), '',
                           align_center=True, rgb=VALUE_RGB))
    parts += [hidden_gauge('TUI_PW_PlayerFatigue', 'PlayerFatigue', 3), hidden_gauge('TUI_PW_PetHP', 'PetHP', 16),
              gauge('TUI_PW_ZealTick', 'ZealTick', TICK_TYPE, (LEFT, TICK_TOP, BAR_WIDTH, TICK_HEIGHT), 'TUI_TickFill',
                    TEXT_RGB, track='TUI_TickTrack')]
    height = 2 * BORDER + RESISTS_TOP + CAPTION_HEIGHT + TEXT_HEIGHT + PLAYER_BOTTOM_GAP
    return window('PlayerWindow', 'Player', height, parts)


def buff_window():
    """Your effects: 15 slots, their names from the stock labels 45 to 59."""
    return effects_table('BuffWindow', 'Effects', 15, 45, 'TUI_BW')


def song_window():
    """Your songs and other short effects: 6 slots, their names from Zeal's labels 135 to 140."""
    return effects_table('ShortDurationBuffWindow', 'Songs', 6, 135, 'TUI_SDBW')


WINDOW_FILES = {GROUP_FILE: group_window, TARGET_FILE: target_window, CASTING_FILE: casting_window,
                CHAT_FILE: chat_window, PET_WINDOW_FILE: pet_window, SELECTOR_FILE: selector_window,
                BUFF_FILE: buff_window, SONG_FILE: song_window, PLAYER_FILE: player_window}


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
        DOT_TEXTURE: Texture(BACKGROUND_SIZE, BACKGROUND_SIZE, (255, 255, 255, GRIP_ALPHA)),
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
    """Builds the skin into out (uifiles/TriageUI by default): the base skin's files plus TriageUI's."""
    uifiles = Path(eq_dir) / 'uifiles'
    base_dir = uifiles / base
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
        raise BuildError(f'Neither {base} nor default has {ANIMATIONS_FILE}')
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
        for source in base_dir.iterdir():
            if source.is_file() and source.name.lower() not in ours:
                shutil.copy2(source, out / source.name)
        for name, data in files.items():
            (out / name).write_bytes(data)
        (out / MARKER_FILE).write_text(
            f'Built by TriageUI\'s build_skin.py from uifiles\\{base}. Rebuild rather than edit: '
            'the script replaces this folder.\n'
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
    print(f'Built {out} from {args.base} with the TriageUI windows.')
    # The 1 keeps the character's window layout; without it windows move to the skin's default spots.
    print(f'In game, type /load {out.name} 1 to use it, or /load {args.base} 1 to go back.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
