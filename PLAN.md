# TriageUI window plan

Every window the Project Quarm client loads, and whether TriageUI has redesigned it yet. The client loads the files listed in `uifiles/default/EQUI.xml`. A window TriageUI hasn't redesigned keeps EverQuest's own look: the client falls back to `uifiles/default` for every file the skin doesn't have.

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
| Item Display | `EQUI_ItemDisplay.xml` |
| Quantity (splitting a stack) | `EQUI_QuantityWnd.xml` |
| Give | `EQUI_GiveWnd.xml` |
| Trade | `EQUI_TradeWnd.xml` |
| Loot | `EQUI_LootWnd.xml` |
| Compass | `EQUI_CompassWnd.xml` |
| Bank | `EQUI_BankWnd.xml` |
| Skills | `EQUI_SkillsWindow.xml` |
| Spell Book | `EQUI_SpellBookWnd.xml` |
| Inventory | `EQUI_Inventory.xml` |
| Tracking | `EQUI_TrackingWnd.xml` |

## To do: everyday

Roughly in order of how much a player sees them.

| Window | File |
|---|---|
| Inspect | `EQUI_InspectWnd.xml` |
| Raid Options | `EQUI_RaidOptionsWindow.xml` |
| Friends | `EQUI_FriendsWnd.xml` |
| Alternate Advancement | `EQUI_AAWindow.xml` |

## To do: occasional

| Window | File |
|---|---|
| Load Skin | `EQUI_LoadskinWnd.xml` |
| Help | `EQUI_HelpWnd.xml` |
| Send Feedback | `EQUI_FeedbackWnd.xml` |
| Training | `EQUI_TrainWindow.xml` |
| Choose a Skill | `EQUI_SkillsSelectWindow.xml` |
| Edit Social | `EQUI_SocialEditWnd.xml` |
| Book (readable books) | `EQUI_BookWindow.xml` |
| Note | `EQUI_NoteWindow.xml` |
| Player Notes | `EQUI_PlayerNotesWindow.xml` |
| Bazaar Vendor | `EQUI_BazaarWnd.xml` |
| Bazaar Search | `EQUI_BazaarSearchWnd.xml` |
| Text Entry | `EQUI_TextEntryWnd.xml` |
| Color Picker | `EQUI_ColorPickerWnd.xml` |
| Alarm | `EQUI_AlarmWnd.xml` |
| Video Modes | `EQUI_VideoModesWnd.xml` |
| Music Player | `EQUI_MusicPlayerWnd.xml` |
| File Selection | `EQUI_FileSelectionWnd.xml` |
| Report a Bug | `EQUI_BugReportWnd.xml` |
| Gems (the minigame) | `EQUI_GemsGameWnd.xml` |
| Cursor attachment (the item on the cursor and its stack count; little to restyle) | `EQUI_CursorAttachment.xml` |

## Left as they are

Seen only before login. TriageUI leaves them to EverQuest's own files.

| Window | File |
|---|---|
| Character Select | `EQUI_CharacterSelect.xml` |
| Character Create | `EQUI_CharacterCreate.xml` |
| Face Pick | `EQUI_FacePick.xml` |

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
