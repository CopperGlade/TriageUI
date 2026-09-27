# TriageUI

EverQuest windows for Project Quarm in the look of the EQ Triage overlays · by Sebik &lt;Europa&gt;

TriageUI restyles EverQuest's own windows with the clean look of [EQ Triage](https://github.com/CopperGlade/EQTriage)'s overlays: a translucent dark panel, a faint rounded edge and plain text. It's a UI skin: it only changes how windows look, and it never plays for you.

It is built one window at a time. **So far it has the target, group, raid, casting, air, chat, pet, window selector, actions, hot button, bag, merchant, effects, songs and player windows, the spell bar and the confirmation dialog.** Everything else keeps the look of the skin you already use (duxaUI by default).

They all sit on the overlays' dark panel, with no title bar, like the overlays with their header bar hidden, except for a really thin one on the chat windows. Drag a window by its background to move it, and a chat window by the thin strip along its top.

The panel is solid, so each window is as see-through as you set it. EverQuest keeps a transparency and a fade for every window, per character: `Alpha` (0 to 255), `FadeToAlpha` (what it fades to when the pointer leaves) and `Fades` in your character's `UI_<name>_pq.proj.ini`. The overlays' look is about `Alpha=217` (85%). Edit that file only while the character is camped: logging in and `/load` rewrite it.

Buttons are a faint wash over the panel with a thin outline, and turn solid slate while you point at them. Their labels are TriageUI's own crisp pixel lettering with room between the letters, since EverQuest's small font looks squished. Buttons side by side are as far apart as the window's edge is from its text.

## The target window

A thin, faint line along the top edge, the color of the bars' faint background, shows the server tick (from Zeal). Under it, the target's name has the whole first line, so long mob names fit. Below it, a thin health bar on a faint background that shows its full length even when it's nearly empty, then the health %. With nothing targeted, only the empty bar shows. It's a little narrower than the other windows and sits well next to EQ Triage's Distance overlay.

Health bars are the name's color, softened to 70% so they don't glare next to the text.

## The group window

As wide as the pet and hot button windows. Each group member is one line: their name, and their health % on the right (only for group slots with someone in them), both in the soft blue of the player window's mana bar, with a thin health bar in the same blue under the name. A faint line separates each member from the one above, as in the effects window. Empty slots show nothing, not even a 0. Under each member, their pet gets a line of its own, indented, with its name smaller and in grey and a thin grey health bar: the game gives skins no number for a pet's health.

**Click anywhere on a row to target that member or pet.** Pet rows are as big as member rows, instead of the hairline pet bars of most skins. A member without a pet leaves their pet row empty.

The buttons along the bottom are **Invite** and **Disband**. While you have an invitation, **Follow** (accept) and **Decline** take their place.

## The raid window

Everyone in your raid in two lists straight on the panel: the players in a group, then, under **Not in a group**, the players in none. Each list shows the group number, name, class and rank (Raid Leader or Group Leader), with each heading on a faint strip like the overlays' header. There's no level column, and the player count and average level are left out. The lists scroll with the same slim scrollbar as the chat windows.

Under the lists are two rows of buttons: **Invite**, **Disband** and **Make Leader**, then **Add Looter**, **Remove Looter** and **Options** (the raid options, where the class colors are set). While you have a raid invitation, **Accept** and **Decline** take the place of Invite and Disband. Point at a button to see what it does.

Unlike EverQuest's own raid window, it has a fixed size, like the other TriageUI windows, so you drag it by its background.

## The casting window

**Casting:** and the spell's name, in a soft red, above a bar in the same red across the whole window that fills as the cast completes. It's as wide as the target window, so the two line up when stacked. The spell's name comes from Zeal. The bar is the countdown: the game doesn't give skins the remaining time as a number.

## The air window

Your air while you're underwater: **Air Remaining**, in a soft cyan, above a bar in the same cyan across the whole window that empties as your air runs out. It's the casting window's size, so the two line up when stacked. The bar is all there is: the game doesn't give skins your air as a number.

## The spell bar

Your memorized spells as a table, like the effects window: a roomy row for each spell gem with its icon and the spell's name, and a faint line under each row. The gem icons are duxaUI's own (or those of the skin you build from). **Click anywhere on a row to cast that spell.**

A thin white bar under a spell's name shows how long until you can cast it again. A soft red bar along the top of the window, the red of the casting window, shows the short global cooldown after every cast. Both come from Zeal.

In a row of its own under the gems, a wide button with a book, across the whole window so it's easy to hit in a hurry, opens and closes your spellbook. It stays lit while the book is open. Zeal's right-click menus are where they always are: right-click an empty gem to pick a spell, or the book button for your spell sets.

## The chat windows

Every chat window is the same: a thin strip along the top with the window's name in small text (EverQuest writes the name there; a skin can't leave it off), the chat straight on the panel with a slim scrollbar of small arrows and a thin thumb, and the line you type on a plain strip along the bottom, a little darker than the window, with a faint outline.

**To move a chat window, drag the thin strip along its top.** Resize it from its edges. The strip is there because EverQuest won't let you drag a resizable window that has no title bar.

## The pet window

Your pet in the target window's shape, as wide as the hot button window: its name on the first line, its health bar and % on the second (the % only while you have a pet), and its commands below in three columns of related pairs: **Attack** over **Back** (fight, stop fighting), **Guard** over **Follow** (hold a spot, stop holding it), and **Taunt** over **Dismiss** (`/pet get lost`). There's no Sit button; type `/pet sit` if you ever need it.

## The window selector

The row of buttons that opens and closes your other windows, each with a simple line icon: **Options** (sliders), **Inventory** (a backpack), **Actions** (crossed swords), **Friends** (two people), **Hotbuttons** (a grid), **Spells** (a wand), **Pet Info** (a paw) and **Effects** (a sparkle). A button stays lit in slate while its window is open. Point at one for its name. There's no Help button.

## The actions window

As wide as the hot button window, with the game's four pages behind a row of icon tabs in the window selector's style: **Main** (a house), **General Skills** (a compass), **Combat Skills** (a sword) and **Socials** (a speech bubble). The open page's tab is lit, and a faint line, like the effects window's, separates the tabs from the page. Point at a tab for its page's name. On every page the actions are two columns of buttons, their names in a small font.

- **Main:** **Camp**, **Sit** or **Stand**, **Run** or **Walk** (the game shows whichever you can switch to), and **Invite**, which becomes **Follow** while you have a group invitation: Follow joins the group. It doesn't follow your target; for that, make a hot button with `/follow`. There's no Who or Disband: use `/who`, or the group window's Disband button.
- **General Skills** (the game's Abilities page): your six skill buttons, such as Sense Heading, Forage or Hide. The game writes each skill's name on its button.
- **Combat Skills** (the game's Combat page): **Melee Attack** and **Range Attack**, then your four combat skills, such as Kick or Taunt.
- **Socials:** six of the twelve socials on each social page, 1 to 3 and 7 to 9, under the page arrows and the page number. Socials 4, 5, 6, 10, 11 and 12 are hidden to keep the window short: put what you need in the slots shown, or on a hot bar.

The window is only as tall as the socials page, the tallest. The game needs all four pages: it sends a button's click to the page that's open, so a button moved to another page would stop working.

## The hot button window

Your hot bar in duxaUI's shape, so everything is where you're used to it, on a grid of square buttons. On the left, the page arrows with the page number between them, and your ten hot buttons under them, two to a row, each with its name in the game's small font (or the item's or spell's icon). On the right, your **Primary** and **Secondary**, **Range** and **Ammo** slots, then your eight bag slots in two columns, 1 to 4 and 5 to 8. An empty weapon slot shows a large, faint icon of what goes there, in the color of the lines between rows elsewhere: a sword, a shield, a bow and an arrow. An empty bag slot is a plain square.

## The bag window

Each bag you open gets its slots two to a row, as in duxaUI, the size of the hot button window's squares, with **Done** across the bottom to close it. A tradeskill container such as a sewing kit or a forge also gets **Combine** above Done. The game sizes the window to each bag, so a 4-slot bag is two rows and a 10-slot bag five. Every bag's window is the same width, and the bag's name isn't shown. You can also close a bag by clicking its slot again or pressing Esc.

## The merchant window

All 80 of a merchant's slots at once, eight to a row on the hot button window's squares, so there's nothing to scroll. Empty slots are plain squares. Under them, past a thin divider, the item you're considering, and across the bottom **Buy** (for the merchant's items) or **Sell** (for yours) and **Done**. The item's name and price come in chat, as always.

When you select one of your own items with charges, Project Quarm's recharge shows beside it: its charges, the price of the next charge, and a **Recharge** button. Point at Recharge for the price per charge. The merchant's name isn't shown. Like the other TriageUI windows, it has a fixed size and you drag it by its background.

## The player window

Just what you need at a glance, as wide as the hot button and actions windows. Your name, **Health** with your health % in the middle of the line, your current/max on the right and your health bar under it in a soft green, then **Mana** the same way, its bar in the soft blue of the group window's names. The numbers are green, like the resists' values, with a white slash between them. Mana's current/max come from Zeal. Then, on one line, **XP/h** at the left and **AA/h** at the right, each followed by its %, from Zeal: the percent of a level, and of an AA point, you're gaining an hour, each averaged over up to the last two hours (both start over when you `/load` a skin; type `/resetexp` to start them over yourself). XP/h counts regular experience only, so it reads 0% while your AA experience is at 100%, and AA/h reads 0% while it's at 0%. Under them, your resists as a small table: **DR**, **PR**, **MR**, **FR** and **CR**, each over its value. The captions are white like your name. Health, Mana, the XP/h line and the resists are spaced evenly apart, so each reads on its own.

## The effects and songs windows

Your effects as a table, like the EQ Triage overlays: a row for each with the time left, the spell icon and its name, and a faint line between rows. A harmful effect's icon gets a red bar on each side (the game gives a skin no way to color the name itself). The Songs window (short effects such as bard songs, with names from Zeal) is the same table with six rows. The time left comes from Zeal's **Buff Timers** option, which draws it at the start of each row, in a column of its own before the icons. Both windows are a little wider than the others, so longer effect names fit. Click anywhere on a row to click that effect off; pointing at a row shows the effect's name.

Each row is inset a little from the window's sides, like the lines between rows. The game places the rows itself and needs that room: rows as wide as the window ignored the pointer altogether.

Both windows share the game's blue and red effect backgrounds with a few other windows. TriageUI replaces them with see-through ones, nothing behind a helpful effect's icon and just the red bars beside a harmful one's, so the spellbook, item display and combat ability windows lose their bright blue and red behind icons too.

## The confirmation dialog

The box that asks before something happens, such as a resurrection, looting a no-drop item, destroying an item or a translocation. The question sits straight on the panel, with room for three lines, and **Yes** and **No** side by side under it. A notice gets **OK** alone, in the middle. It's as wide as the window selector, so most questions fit on two lines. The game puts it in the middle of the screen. For a question with a time limit, such as a resurrection, Zeal shows the time left at its top right corner.

## Install

1. **Install Python 3** on Windows from [python.org](https://www.python.org/downloads/) if you don't have it. Nothing else is needed.
2. **Get TriageUI.** Click **Code → Download ZIP** on this page and extract it anywhere, for example `C:\TriageUI`.
3. **Build the skin.** Open a command prompt in that folder and run:

   ```
   python build_skin.py
   ```

   It reads your EverQuest folder at `C:\QUARM` and creates `C:\QUARM\uifiles\TriageUI`: a copy of your duxaUI skin with the TriageUI windows added. Your duxaUI folder is never changed.
4. **Load it in game.** Type `/load TriageUI 1`. To go back, type `/load duxaUI 1`.

   The `1` keeps your window layout. EverQuest saves where your windows are per character, not per skin (in `UI_Sebik_pq.proj.ini` for Sebik, in your EverQuest folder), so every skin can use the same layout. The **Load Skin** window does the same when **Keep Your Layout** is ticked.

> [!WARNING]
> **Never leave out the `1`.** `/load` saves your current window positions before it loads, and without the `1` the windows jump to the skin's default spots. After that, even `/load duxaUI 1` only brings back the jumbled positions, because they're what was saved. Copy your character's `UI_<name>_pq.proj.ini` somewhere safe before trying a new skin.

### Options

| Option | Meaning |
|---|---|
| `--eq D:\Games\QUARM` | Your EverQuest folder, if it isn't `C:\QUARM`. |
| `--base default` | The skin to start from, if you don't use duxaUI. It must be a folder in `uifiles`. |
| `--out PATH` | Where to build, instead of `uifiles\TriageUI`. |

> [!NOTE]
> **Build again after Project Quarm's patcher updates duxaUI**, so TriageUI picks up the new files. Building replaces the whole `TriageUI` folder, so don't edit files in it.

## Limits

- **Fonts:** EverQuest windows can only use the game's built-in fonts, so the text is EverQuest's font rather than the overlays' Segoe UI.
- **Colors that change:** a skin sets each text's color once, so names stay white (pets grey). The overlays color names yellow and red at low health, and Zeal colors target rings by con, but a skin can do neither.
- **The red box around the player window while you auto-attack:** EverQuest draws it itself, a 1px red outline that flashes on top of the window, and no skin setting turns it off.
- **The name of the item you're considering at a merchant:** EverQuest shows it only in chat. The merchant window gets the item's icon and nothing else, so no skin can show the name.

## Troubleshooting

- **`There is no skin folder C:\QUARM\uifiles\duxaUI`:** your EverQuest folder is elsewhere (use `--eq`), or you use another skin (use `--base` with its folder name).
- **`...TriageUI already exists and wasn't built by this script`:** a `TriageUI` folder that TriageUI didn't create is in the way. Rename it; the builder never overwrites it.
- **`Couldn't write ...`:** EverQuest may be using the folder. Type `/load duxaUI`, build again, then `/load TriageUI`.
- **The game crashes while logging in or loading TriageUI:** EverQuest loads the skin your character last used at every login, so a skin that crashes it crashes every login. While logged out, open `UI_<name>_pq.proj.ini` in your EverQuest folder and change `UISkin=triageui` under `[Main]` to `UISkin=duxaUI`, then build again once there's a fix. The crash report in `crashes` in your EverQuest folder shows where it happened.
- **Something looks wrong in game:** `UIErrors.txt` in your EverQuest folder lists skin problems. Lines that mention `TargetWindow`, `GroupWindow`, `CastingWindow`, `CastSpellWnd`, `ChatWindow`, `PetInfoWindow`, `SelectorWindow`, `ActionsWindow`, `HotButtonWnd`, `ContainerWindow`, `MerchantWnd`, `BuffWindow`, `ShortDurationBuffWindow`, `PlayerWindow`, `BreathWindow`, `RaidWindow`, `ConfirmationDialogBox` or `TUI_` are about TriageUI.
- **An effect won't click off:** a left click anywhere on its row does it. If pointing at a row shows no name, the game isn't seeing the rows at all: rebuild the skin (older builds had rows as wide as the window, which the game ignores). Otherwise make sure Zeal's **Buff click thru** option (Zeal options, General tab) is off, or unlock the window.
- **After building again:** type `/reloadskin` (from Zeal) to see the changes. It reloads the skin with your saved layout, like `/load TriageUI 1`.

## Development

The builder uses only Python's standard library. The tests also need Pillow and pytest:

```
pip install -r requirements-dev.txt
python -m pytest tests
```
