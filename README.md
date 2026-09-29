# TriageUI

EverQuest windows for Project Quarm in the look of the EQ Triage overlays · v1.0.0 · by Sebik &lt;Europa&gt;

TriageUI restyles EverQuest's own windows with the clean look of [EQ Triage](https://github.com/CopperGlade/EQTriage)'s overlays: a translucent dark panel, a faint rounded edge and plain text. It's a UI skin: it only changes how windows look, and it never plays for you.

It is built one window at a time. **So far it has the target, group, raid, casting, air, chat, pet, window selector, actions, hot button, bag, inventory, merchant, item, effects, songs, player, quantity, give, trade, loot, bank and skills windows, the spell bar, the spell book, the confirmation dialog and the compass.** Everything else keeps EverQuest's own look.

They all sit on the overlays' dark panel, with no title bar, like the overlays with their header bar hidden, except for a really thin one on the chat windows and one with a **Close** button on the item and quantity windows. Drag a window by its background to move it, and a chat, item or quantity window by the strip along its top.

The panel is solid, so each window is as see-through as you set it. EverQuest keeps a transparency and a fade for every window, per character: `Alpha` (0 to 255), `FadeToAlpha` (what it fades to when the pointer leaves) and `Fades` in your character's `UI_<name>_pq.proj.ini`. The overlays' look is about `Alpha=217` (85%). Edit that file only while the character is camped: logging in and `/load` rewrite it.

Buttons are a faint wash over the panel with a thin outline, and turn solid slate while you point at them. Most buttons' labels are TriageUI's own crisp pixel lettering with room between the letters. The actions window, the confirmation dialog and the quantity, merchant, give, trade, loot and inventory windows have taller buttons that show their names in EverQuest's own small font instead, which is easier to read. The **Close** button on the item and quantity windows' title bars matches them. Buttons side by side are as far apart as the window's edge is from its text.

## The target window

The target's name has the whole first line, so long mob names fit. Below it, a thin health bar on a faint background that shows its full length even when it's nearly empty, then the health %. With nothing targeted, only the empty bar shows. It's a little narrower than the other windows and sits well next to EQ Triage's Distance overlay.

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

Your memorized spells as a table, like the effects window: a roomy row for each spell gem with its icon and the spell's name, and a faint line under each row. The gem icons are EverQuest's own. **Click anywhere on a row to cast that spell.**

A thin white bar under a spell's name shows how long until you can cast it again. A soft red bar along the top of the window, the red of the casting window, shows the short global cooldown after every cast. Both come from Zeal.

In a row of its own under the gems, a wide button with a book, across the whole window so it's easy to hit in a hurry, opens and closes your spellbook. It stays lit while the book is open. Zeal's right-click menus are where they always are: right-click an empty gem to pick a spell, or the book button for your spell sets.

## The spell book

Your spell book in the spell bar's look: the two open pages side by side with a thin line between them, and each spell a row with its icon and then its name, like a spell gem's row. There's room for the longest spell name any class can scribe. Empty spots stay blank. **Click anywhere on a spell's row**, its icon or its name, as you would click its icon in EverQuest's own book.

While you memorize or scribe a spell, a thin soft red bar along the top of the window shows how far along it is, like the spell bar's bar along its top. Along the bottom are the page arrows at each end, each page's number beside its arrow, and **Done** in the middle. The window has a fixed size. There's no title bar or close box: drag the window by its background, and click Done or the spell bar's book button to close it.

## The chat windows

Every chat window is the same: a thin strip along the top with the window's name in small text in the middle (EverQuest writes the name there; a skin can't leave it off) and a small **X** at the right end that closes the window, the chat straight on the panel with a slim scrollbar of small arrows and a thin thumb, and the line you type on a plain strip along the bottom, a little darker than the window, with a faint outline.

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

## The inventory window

Your gear is laid out as in EverQuest's own inventory, on the hot button window's squares:
- ears, neck, head and face along the top;
- chest, arms, wrist, waist and ring down the left side;
- back, shoulders, wrist, hands and ring down the right side;
- legs and feet between the rings, and your weapons under them.

An empty slot shows a large, faint icon of what goes there, like the hot button window's weapon slots.

The middle shows your name, your level and class, and your deity in grey. Under them are your **XP** and **AA**, each with the % of the way to your next level or AA point and a bar under it. Drop an item anywhere in the middle to equip it.

On the right, past a thin line:
- your stats, then your **AC** and **ATK**, then your **Weight**, each group under a thin line, with the numbers in green as in the player window;
- your coin boxes, marked **pp**, **gp**, **sp** and **cp** as in the give window. They're wide enough for a large amount of platinum; click one to pick up some coins.

Your HP and resists are in the player window, and your bag slots in the hot button window.

Along the bottom:
- **Skills** and **AA** open those windows;
- **Destroy** destroys the item you're holding;
- **Done** closes the window.

The window has a fixed size, with no title bar or close box: drag it by its background.

## The merchant window

All 80 of a merchant's slots at once, eight to a row on the hot button window's squares, so there's nothing to scroll. Empty slots are plain squares. Under them, past a thin divider, the item you're considering, and across the bottom **Buy** (for the merchant's items) or **Sell** (for yours) and **Done**. The item's name and price come in chat, as always.

When you select one of your own items with charges, Project Quarm's recharge shows beside it: its charges, the price of the next charge, and a **Recharge** button. Point at Recharge for the price per charge. The merchant's name isn't shown. Like the other TriageUI windows, it has a fixed size and you drag it by its background.

## The item window

What you see when you right-click an item, or a spell with Zeal's spell info on. The item's name is on a title bar along the top, with a **Close** button at its right end, the same size as the quantity window's **Accept**. Under it, the item's icon sits in the top left corner, with its details in a column beside it, straight on the panel. When the details don't all fit, they scroll with the chat windows' slim scrollbar, or with Page Up and Page Down. Zeal's extra item windows, which let you keep several open, look the same.

The window has a fixed size, like the other TriageUI windows. **Drag it by its title bar.** EverQuest writes the name on the bar itself, in its own color, since the details never include it.

## The player window

Just what you need at a glance, as wide as the hot button and actions windows. **Health** at the top, with your health % in the middle of the line, your current/max on the right and your health bar under it in a soft green, then **Mana** the same way, its bar in the soft blue of the group window's names. Just under the mana bar, a thin white line shows the server tick (from Zeal): it drains to empty at each tick, the moment your mana and health come in, so you can stand up to cast right after one. Type `/tickreverse` to have it fill up to the tick instead. The numbers are green, like the resists' values, with a white slash between them. Mana's current/max come from Zeal. Then, on one line, **XP/h** at the left and **AA/h** at the right, each followed by its %, from Zeal: the percent of a level, and of an AA point, you're gaining an hour, each averaged over up to the last two hours (both start over when you `/load` a skin; type `/resetexp` to start them over yourself). XP/h counts regular experience only, so it reads 0% while your AA experience is at 100%, and AA/h reads 0% while it's at 0%. Under them, your resists as a small table: **DR**, **PR**, **MR**, **FR** and **CR**, each over its value. The captions are white. Health, Mana, the XP/h line and the resists are spaced evenly apart, so each reads on its own.

## The effects and songs windows

Your effects as a table, like the EQ Triage overlays: a row for each with the time left, the spell icon and its name, and a faint line between rows. A harmful effect's icon gets a red bar on each side (the game gives a skin no way to color the name itself). The Songs window (short effects such as bard songs, with names from Zeal) is the same table with six rows. The time left comes from Zeal's **Buff Timers** option, which draws it at the start of each row, in a column of its own before the icons. Both windows are a little wider than the others, so longer effect names fit. Click anywhere on a row to click that effect off; pointing at a row shows the effect's name.

Each row is inset a little from the window's sides, like the lines between rows. The game places the rows itself and needs that room: rows as wide as the window ignored the pointer altogether.

Both windows share the game's blue and red effect backgrounds with a few other windows. TriageUI replaces them with see-through ones, nothing behind a helpful effect's icon and just the red bars beside a harmful one's, so the combat ability window loses its bright blue and red behind icons too. The item window puts them behind a spell's icon too.

## The confirmation dialog

The box that asks before something happens, such as a resurrection, looting a no-drop item, destroying an item or a translocation. Since these matter, it has twice the usual room inside, around the question and above and below the buttons. The question sits straight on the panel, with room for three lines, and **Yes** and **No** side by side under it, as big as the actions window's buttons and with their names in the same small font. A notice gets **OK** alone, in the middle. It's as wide as the window selector, so most questions fit on two lines. The game puts it in the middle of the screen. For a question with a time limit, such as a resurrection, Zeal shows the time left at its top right corner.

## The quantity window

What EverQuest asks when you pick up part of a stack, or some of your coins. It has the item window's title bar, with **Quantity** at the left and **Close** at the right. Under it, a slider runs across the window: a small knob on a faint line, which you drag, or click anywhere on the line to jump there. Under that, the number and **Accept** side by side. Like the confirmation dialog, it has twice the usual room inside. It's as wide as the hot button window, and the game opens it at the slot you clicked, with the whole stack filled in.

The number takes digits only. What you type is added after the number that's there, so delete it first (Backspace) to type a new one. Press Enter or click **Accept** to take that many. Click **Close** or press Esc to close the window without taking any. Drag it by its title bar or its background.

## The give window

What opens when you hand an NPC an item or some coins. The NPC's name is along the top, so you can see who gets them; a very long name is cut off. Under it, your four item slots sit in a row on the hot button window's squares. Then come the coin boxes, two to a row, **pp** and **gp**, then **sp** and **cp**, each showing how many of that coin you're giving. The coin's name is as big as the amount and level with it. To give coins, pick them up from your inventory and drop them on their box. **Give** and **Cancel** are along the bottom, under a thin line, each half the window wide, so there's room around their names. The window is as wide as the hot button window and has a fixed size. There's no title bar or close box: drag the window by its background, and click Cancel to close it.

## The trade window

What opens when you trade with another player. What they offer is on the left, under their name, and what you offer is on the right, under yours, with a thin line between the two sides. Each side has its eight item slots, two to a row, and under them its coin boxes, one to a row, marked **pp**, **gp**, **sp** and **cp** as in the give window. An amount of 100,000 or more of one coin runs into its name. To offer coins, pick them up from your inventory and drop them on one of your boxes; the other side's boxes only show what they offer. **Trade** and **Cancel** are along the bottom, under a thin line across the window, as in the give window. The window has a fixed size. There's no title bar or close box: drag the window by its background, and click Cancel to close it.

## The loot window

What opens when you loot a corpse. The corpse's name is along the top. Under it, all 30 of its slots sit six to a row on the hot button window's squares, so there's nothing to scroll. Empty slots are plain squares. Along the bottom are **Link All**, which puts a link to every item in your chat line, **Loot All**, which takes everything, and **Done**. Link All and Loot All are Zeal's, the same as `/linkall` and `/lootall`. The window has a fixed size. There's no title bar or close box: drag the window by its background, and click Done to close it.

## The bank window

What opens when you talk to a banker. The shared bank is on the left, its ten slots two to a row under **Shared Bank**, and your own bank is on the right, all 30 slots six to a row under the banker's name, with a thin line between the two. Both keep EverQuest's own order, down each column, so your items sit where you're used to seeing them. Under your slots are your bank's coin boxes, marked **pp**, **gp**, **sp** and **cp** as in the give window and wide enough for a large amount of platinum. Drop coins from your inventory on a box to bank them, or click a box to take some out. Under the shared slots are **Change**, Zeal's button for changing your coins, your bank's and then your inventory's, and **Done**. The window has a fixed size. There's no title bar or close box: drag the window by its background, and click Done to close it.

## The skills window

Your skills and their values in one list straight on the panel, with each heading on a faint strip like the raid window's. Click **Skill** or **Value** to sort the list by it, and again to reverse it (a Zeal feature). There's no rank column, the word such as Very Good or Master beside each value. About 24 skills are in view, and the rest scroll with the same slim scrollbar as the chat windows. **Done** is along the bottom. The window has a fixed size. There's no title bar or close box: drag the window by its background, and click Done to close it.

## The compass

A strip of directions slides past a thin soft red line in the middle as you turn: the direction under the line is the way you face. **N**, **E**, **S** and **W** each have a taller tick under them, with **N** in the same soft red as the line, so north stands out, and **NE**, **SE**, **SW** and **NW** sit between them in grey. A faint tick marks every 10°. The strip moves at EverQuest's own scale, so about half the circle is in view, and it fades out toward the window's sides. It's the size of EverQuest's own compass, with no title bar: drag it by any part.

## Install

1. **Get TriageUI.** Download `TriageUI-vX.Y.Z.zip` from the [latest release](https://github.com/CopperGlade/TriageUI/releases/latest).
2. **Put it in your EverQuest folder.** Open the zip and drag the `TriageUI` folder inside it into `C:\QUARM\uifiles`, so you have `C:\QUARM\uifiles\TriageUI`. It holds only TriageUI's own windows and art: for every other window, EverQuest uses its own UI files. Your other skins are never changed.
3. **Load it in game.** Type `/load TriageUI 1`. To go back, type `/load` with your old skin's name and the `1`, such as `/load duxaUI 1`.

   The `1` keeps your window layout. EverQuest saves where your windows are per character, not per skin (in `UI_Sebik_pq.proj.ini` for Sebik, in your EverQuest folder), so every skin can use the same layout. The **Load Skin** window does the same when **Keep Your Layout** is ticked.

> [!WARNING]
> **Never leave out the `1`.** `/load` saves your current window positions before it loads, and without the `1` the windows jump to the skin's default spots. After that, even `/load duxaUI 1` only brings back the jumbled positions, because they're what was saved. Copy your character's `UI_<name>_pq.proj.ini` somewhere safe before trying a new skin.

### Updating

1. Download the newest `TriageUI-vX.Y.Z.zip` from the [latest release](https://github.com/CopperGlade/TriageUI/releases/latest).
2. Delete your old `C:\QUARM\uifiles\TriageUI` folder, so nothing of the old version is left, then drag the new one from the zip into `C:\QUARM\uifiles` as when installing.
3. In game, type `/reloadskin` (from Zeal), or `/load TriageUI 1`.

Your window layout is kept: EverQuest saves it per character in your EverQuest folder, not in the skin. `TriageUI.txt` in the skin's folder says which version you have.

> [!NOTE]
> TriageUI's `EQUI_Animations.xml` is EverQuest's own with TriageUI's pieces added. If Project Quarm's patcher ever changes `uifiles\default\EQUI_Animations.xml`, get the next release or build TriageUI yourself, so it picks up the change. Don't edit the files in the `TriageUI` folder: updating and building replace them.

### Building it yourself

The release's `TriageUI` folder is built on EverQuest's own UI files. To build it on another skin of yours, so the windows TriageUI hasn't redesigned take that skin's look, or for an EverQuest folder that isn't `C:\QUARM`, build it yourself:

1. **Install Python 3** on Windows from [python.org](https://www.python.org/downloads/) if you don't have it. Nothing else is needed.
2. Download the release's **Source code (zip)** and extract it anywhere.
3. Open a command prompt in the extracted folder and run `python build_skin.py`, with any of the options below. It reads your EverQuest folder at `C:\QUARM`, replaces `C:\QUARM\uifiles\TriageUI` and prints the version it built.

| Option | Meaning |
|---|---|
| `--eq D:\Games\QUARM` | Your EverQuest folder, if it isn't `C:\QUARM`. |
| `--base NAME` | Build on another skin, a folder in `uifiles`, so the windows TriageUI hasn't redesigned take its look instead of EverQuest's own. |
| `--out PATH` | Where to build, instead of `uifiles\TriageUI`. |

## Limits

- **Fonts:** EverQuest windows can only use the game's built-in fonts, so the text is EverQuest's font rather than the overlays' Segoe UI.
- **Colors that change:** a skin sets each text's color once, so names stay white (pets grey). The overlays color names yellow and red at low health, and Zeal colors target rings by con, but a skin can do neither.
- **The red box around the player window while you auto-attack:** EverQuest draws it itself, a 1px red outline that flashes on top of the window, and no skin setting turns it off.
- **The name of the item you're considering at a merchant:** EverQuest shows it only in chat. The merchant window gets the item's icon and nothing else, so no skin can show the name.
- **The item window's title bar:** EverQuest writes the item's name in its own color and places the Close button itself, a little further from the window's edge than TriageUI's usual spacing. A skin sets neither.

## Troubleshooting

- **Windows won't delete or replace the `TriageUI` folder,** or building it yourself says **`Couldn't write ...`:** EverQuest may be using the folder. Type `/load default 1`, replace or build it, then `/load TriageUI 1`.
- **Building it yourself says `There is no skin folder C:\QUARM\uifiles\default`:** your EverQuest folder is elsewhere (use `--eq`). With `--base`, the skin you named isn't a folder in `uifiles`.
- **Building it yourself says `...TriageUI already exists and wasn't built by this script`:** a `TriageUI` folder that TriageUI didn't create is in the way. Rename it; the builder never overwrites it.
- **The game crashes while logging in or loading TriageUI:** EverQuest loads the skin your character last used at every login, so a skin that crashes it crashes every login. While logged out, open `UI_<name>_pq.proj.ini` in your EverQuest folder and change `UISkin=triageui` under `[Main]` to `UISkin=default`, then update TriageUI once there's a fix. The crash report in `crashes` in your EverQuest folder shows where it happened.
- **Something looks wrong in game:** `UIErrors.txt` in your EverQuest folder lists skin problems. Lines that mention `TargetWindow`, `GroupWindow`, `CastingWindow`, `CastSpellWnd`, `ChatWindow`, `PetInfoWindow`, `SelectorWindow`, `ActionsWindow`, `HotButtonWnd`, `ContainerWindow`, `MerchantWnd`, `BuffWindow`, `ShortDurationBuffWindow`, `PlayerWindow`, `BreathWindow`, `RaidWindow`, `ConfirmationDialogBox`, `ItemDisplayWindow`, `QuantityWnd`, `GiveWnd`, `TradeWnd`, `LootWnd`, `CompassWindow`, `BankWnd`, `SkillsWindow`, `SpellBookWnd`, `InventoryWindow` or `TUI_` are about TriageUI.
- **An effect won't click off:** a left click anywhere on its row does it. If pointing at a row shows no name, the game isn't seeing the rows at all: update TriageUI (older builds had rows as wide as the window, which the game ignores). Otherwise make sure Zeal's **Buff click thru** option (Zeal options, General tab) is off, or unlock the window.
- **After updating or building again:** type `/reloadskin` (from Zeal) to see the changes. It reloads the skin with your saved layout, like `/load TriageUI 1`.

## Credits

A few of TriageUI's windows borrow ideas from duxaUI, Duxa's skin based on Savok's port of VertUI: the hot button window's shape, with your weapon and bag slots beside the hot buttons, bag slots two to a row, the loot window's **Link All** and **Loot All**, and the bank window's **Change**. TriageUI includes none of duxaUI's files: its windows and art are its own, and everything else is EverQuest's. Its `EQUI_Animations.xml` is EverQuest's own with TriageUI's pieces added, as a skin's must be.

## Development

The builder uses only Python's standard library. The tests also need Pillow and pytest:

```
pip install -r requirements-dev.txt
python -m pytest tests
```

To look at the windows without starting the game, `tools/preview.py` draws them as PNGs with sample text and values (Pillow). With no arguments it draws every window into `build/preview`; give it a word from a window's file name to draw just that one:

```
python tools/preview.py quantity
```
