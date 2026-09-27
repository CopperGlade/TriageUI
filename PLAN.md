# TriageUI window plan

Every window the Project Quarm client loads, and whether TriageUI has redesigned it yet. The client loads the files listed in `uifiles/default/EQUI.xml`. A window TriageUI hasn't redesigned keeps the base skin's look: duxaUI's copy when duxaUI has one, default's otherwise ("Look now" below, with duxaUI as the base).

Windows are redesigned one at a time, and each is checked in game before the next. When a window is finished, move its row to **Done** in the same change. The tests check this list against the windows the builder writes (`WINDOW_FILES` in `build_skin.py`).

## Done

| Window | File |
|---|---|
| Target | `EQUI_TargetWindow.xml` |
| Group | `EQUI_GroupWindow.xml` |
| Raid | `EQUI_RaidWindow.xml` |
| Casting | `EQUI_CastingWindow.xml` |
| Air Remaining | `EQUI_BreathWindow.xml` |
| Chat | `EQUI_ChatWindow.xml` |
| Pet Info | `EQUI_PetInfoWindow.xml` |
| Window Selector | `EQUI_SelectorWnd.xml` |
| Actions | `EQUI_ActionsWindow.xml` |
| Hot Buttons | `EQUI_HotButtonWnd.xml` |
| Bag | `EQUI_Container.xml` |
| Effects | `EQUI_BuffWindow.xml` |
| Songs | `EQUI_ShortDurationBuffWindow.xml` |
| Player | `EQUI_PlayerWindow.xml` |
| Spell bar | `EQUI_CastSpellWnd.xml` |
| Merchant | `EQUI_MerchantWnd.xml` |
| Confirmation dialog | `EQUI_ConfirmationDialog.xml` |

## To do: everyday

Roughly in order of how much a player sees them.

| Window | File | Look now |
|---|---|---|
| Inventory | `EQUI_Inventory.xml` | duxaUI |
| Item Display | `EQUI_ItemDisplay.xml` | duxaUI, without the bright slot bar (TriageUI restyles the slot backgrounds) |
| Spell Book | `EQUI_SpellBookWnd.xml` | duxaUI, without the bright slot bars |
| Loot | `EQUI_LootWnd.xml` | duxaUI |
| Bank | `EQUI_BankWnd.xml` | duxaUI |
| Trade | `EQUI_TradeWnd.xml` | duxaUI |
| Give | `EQUI_GiveWnd.xml` | duxaUI |
| Inspect | `EQUI_InspectWnd.xml` | duxaUI |
| Skills | `EQUI_SkillsWindow.xml` | duxaUI |
| Compass | `EQUI_CompassWnd.xml` | duxaUI |
| Tracking | `EQUI_TrackingWnd.xml` | duxaUI |
| Raid Options | `EQUI_RaidOptionsWindow.xml` | duxaUI |
| Quantity (splitting a stack) | `EQUI_QuantityWnd.xml` | default |
| Friends | `EQUI_FriendsWnd.xml` | default |
| Alternate Advancement | `EQUI_AAWindow.xml` | default |

## To do: occasional

| Window | File | Look now |
|---|---|---|
| Load Skin | `EQUI_LoadskinWnd.xml` | duxaUI |
| Help | `EQUI_HelpWnd.xml` | duxaUI |
| Send Feedback | `EQUI_FeedbackWnd.xml` | duxaUI |
| Training | `EQUI_TrainWindow.xml` | default |
| Choose a Skill | `EQUI_SkillsSelectWindow.xml` | default |
| Edit Social | `EQUI_SocialEditWnd.xml` | default |
| Book (readable books) | `EQUI_BookWindow.xml` | default |
| Note | `EQUI_NoteWindow.xml` | default |
| Player Notes | `EQUI_PlayerNotesWindow.xml` | default |
| Bazaar Vendor | `EQUI_BazaarWnd.xml` | default |
| Bazaar Search | `EQUI_BazaarSearchWnd.xml` | default |
| Text Entry | `EQUI_TextEntryWnd.xml` | default |
| Color Picker | `EQUI_ColorPickerWnd.xml` | default |
| Alarm | `EQUI_AlarmWnd.xml` | default |
| Video Modes | `EQUI_VideoModesWnd.xml` | default |
| Music Player | `EQUI_MusicPlayerWnd.xml` | default |
| File Selection | `EQUI_FileSelectionWnd.xml` | default |
| Report a Bug | `EQUI_BugReportWnd.xml` | default |
| Gems (the minigame) | `EQUI_GemsGameWnd.xml` | default |
| Cursor attachment (the item on the cursor and its stack count; little to restyle) | `EQUI_CursorAttachment.xml` | duxaUI |

## To do: before login

| Window | File | Look now |
|---|---|---|
| Character Select | `EQUI_CharacterSelect.xml` | default |
| Character Create | `EQUI_CharacterCreate.xml` | default |
| Face Pick | `EQUI_FacePick.xml` | default |

## Out of reach

A skin can't change these: Zeal's copies in `uifiles/zeal` override every skin.

| Window | File |
|---|---|
| Options, and its tabs (`EQUI_Tab_*.xml`) | `EQUI_OptionsWindow.xml` |
| Zeal Options | `EQUI_ZealOptions.xml` |
| Zeal Map | `EQUI_ZealMap.xml` |
| Zeal buttons | `EQUI_ZealButtonWnd.xml` |
| Zeal input dialog | `EQUI_ZealInputDialog.xml` |
| Zone Select | `EQUI_ZoneSelect.xml` |
| Guild Management | `EQUI_GuildManagementWnd.xml` |

`uifiles/default` also holds about 70 later-era window files that aren't in its `EQUI.xml` (Bandolier, Tradeskill, Target of Target, Leadership, Tasks, Mail, the map view and more). This client never loads them, so they aren't listed.
