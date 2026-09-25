# TriageUI

EverQuest windows for Project Quarm in the look of the EQ Triage overlays · by Sebik &lt;Europa&gt;

TriageUI restyles EverQuest's own windows with the clean look of [EQ Triage](https://github.com/CopperGlade/EQTriage)'s overlays: a translucent dark panel, a faint rounded edge and plain text. It's a UI skin: it only changes how windows look, and it never plays for you.

It is built one window at a time. **So far it has the target, group, casting, chat, pet, window selector, effects, songs and player windows.** Everything else keeps the look of the skin you already use (duxaUI by default).

They all sit on the overlays' dark panel, with no title bar, like the overlays with their header bar hidden. Drag a window by its background to move it.

The panel is solid, so each window is as see-through as you set it. EverQuest keeps a transparency and a fade for every window, per character: `Alpha` (0 to 255), `FadeToAlpha` (what it fades to when the pointer leaves) and `Fades` in your character's `UI_<name>_pq.proj.ini`. The overlays' look is about `Alpha=217` (85%). Edit that file only while the character is camped: logging in and `/load` rewrite it.

Buttons are a faint wash over the panel with a thin outline, and turn solid slate while you point at them. Their labels are TriageUI's own crisp pixel lettering with room between the letters, since EverQuest's small font looks squished. Buttons side by side are as far apart as the window's edge is from its text.

## The target window

The target's name has the whole first line, so long mob names fit. Below it, a thin health bar on a faint background that shows its full length even when it's nearly empty, then the health %. With nothing targeted, only the empty bar shows. It's a little narrower than the other windows and sits well next to EQ Triage's Distance overlay.

Health bars are the name's color, softened to 70% so they don't glare next to the text.

## The group window

Each group member is one line: their name, and their health % on the right (only for group slots with someone in them). No bars, to keep the window short. A faint line separates each member from the one above, as in the effects window. Empty slots show nothing, not even a 0. Under each member, their pet gets a line of its own, indented, with its name smaller and in grey and a thin health bar: the game gives skins no number for a pet's health.

**Click anywhere on a row to target that member or pet.** Pet rows are as big as member rows, instead of the hairline pet bars of most skins. A member without a pet leaves their pet row empty.

The buttons along the bottom are **Invite** and **Disband**. While you have an invitation, **Follow** (accept) and **Decline** take their place.

## The casting window

**Casting:** and the spell's name, in a soft red, above a bar across the whole window that fills as the cast completes. It's the target window's size, so the two line up when stacked. The spell's name comes from Zeal. The bar is the countdown: the game doesn't give skins the remaining time as a number.

## The chat windows

Every chat window is the same: no title bar (you know which window you chat in), the chat straight on the panel with a slim scrollbar of small arrows and a thin thumb, and the line you type on a plain strip along the bottom, a little darker than the window, with a faint outline.

**To move a chat window, drag the dotted spot in its bottom right corner** (between the dots). Resize it from its edges.

## The pet window

Your pet in the target window's shape, a pixel wider so its three columns of buttons come out even: its name on the first line, its health bar and % on the second (the % only while you have a pet), and its commands below in three columns of related pairs: **Attack** over **Back** (fight, stop fighting), **Guard** over **Follow** (hold a spot, stop holding it), and **Taunt** over **Dismiss** (`/pet get lost`). There's no Sit button; type `/pet sit` if you ever need it.

## The window selector

The row of buttons that opens and closes your other windows, each with a simple line icon: **Options** (sliders), **Inventory** (a backpack), **Actions** (crossed swords), **Friends** (two people), **Hotbuttons** (a grid), **Spells** (a wand), **Pet Info** (a paw) and **Effects** (a sparkle). A button stays lit in slate while its window is open. Point at one for its name. There's no Help button.

## The player window

Just what you need at a glance. A thin bar along the top edge shows the server tick (from Zeal). Then your name, **Health** with your current/max on the right and your health bar under it, then **Mana** the same way, its bar in a soft blue. The current numbers are green, like the resists' values. Mana's numbers come from Zeal. Under them, your resists as a small table: **DR**, **PR**, **MR**, **FR** and **CR**, each over its value.

## The effects and songs windows

Your effects as a table, like the EQ Triage overlays: a row for each with the time left, the spell icon and its name, and a faint line between rows. Harmful effects get a faint red row. The Songs window (short effects such as bard songs, with names from Zeal) is the same table with six rows. The time left comes from Zeal's **Buff Timers** option, which draws it at the start of each row. Click anywhere on a row to click that effect off.

Both windows share the game's blue and red effect backgrounds with a few other windows. TriageUI replaces them with a clear and a faint red one, so the spellbook, item display and combat ability windows lose their bright blue and red behind icons too.

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

## Troubleshooting

- **`There is no skin folder C:\QUARM\uifiles\duxaUI`:** your EverQuest folder is elsewhere (use `--eq`), or you use another skin (use `--base` with its folder name).
- **`...TriageUI already exists and wasn't built by this script`:** a `TriageUI` folder that TriageUI didn't create is in the way. Rename it; the builder never overwrites it.
- **`Couldn't write ...`:** EverQuest may be using the folder. Type `/load duxaUI`, build again, then `/load TriageUI`.
- **Something looks wrong in game:** `UIErrors.txt` in your EverQuest folder lists skin problems. Lines that mention `TargetWindow`, `GroupWindow`, `CastingWindow`, `ChatWindow`, `PetInfoWindow`, `SelectorWindow`, `BuffWindow`, `ShortDurationBuffWindow`, `PlayerWindow` or `TUI_` are about TriageUI.
- **After building again:** type `/reloadskin` (from Zeal) to see the changes. It reloads the skin with your saved layout, like `/load TriageUI 1`.

## Development

The builder uses only Python's standard library. The tests also need Pillow and pytest:

```
pip install -r requirements-dev.txt
python -m pytest tests
```
