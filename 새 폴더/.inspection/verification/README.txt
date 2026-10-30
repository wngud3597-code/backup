Independent verification model — not the distributed Battle SSAFY engine.

Scope:
- Static opponents; axis-aligned shells stop at the first non-G/S/W cell.
- Shell range 3; normal damage 30, mega damage 70.
- G/S movement only; entering S costs 10 HP.
- Friendly tanks/turret and R are monitored as prohibited shot targets.
- Supplied engine IL confirms any shell removes one tree.
- Supplied engine IL confirms a valid adjacent supply answer gives one mega
  shell, up to 10, and default Caesar decode shift is +9.
- X destruction completes an attack scenario. No win-rate claim is possible.
- Multiplayer turns, attack from enemies and launch transport are excluded.

Scenarios:
- Single/team starts, both turret corners, 10/13/20 cell maps.
- Indestructible rock detours, water transmission, low-HP sand detours.
- Allied tank / friendly turret / rock blocking a direct line to X.
- Visible enemy tanks in range should be attacked before continuing to X,
  unless an immediate turret destruction is available. Out-of-range tanks
  should not replace X as the travel objective.
- No ammo and fully boxed-in states must still return a valid command without
  raising an exception; the official S fallback can be used if needed.

Once Bot.choose(state) is stable, unittest should assert:
1. All returned commands parse and the program stays alive.
2. Friendly_shots == rock_shots == no_ammo_shots == forbidden_moves == 0.
3. Static, reachable X scenarios finish within a bounded number of actions.
4. Low-HP sand paths keep hp > 0.
5. Every-shot blocked-line tests inspect the first collision, not just direction.
6. Replay/packet framing tests separately exercise fragmented TCP receives,
   launcher prefix, INIT, and terminal status without invoking the real game.

The model intentionally allows S to return control in impossible states.
Competition-specific penalties for S must be reported separately if applicable.
