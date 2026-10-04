WORLD//ERROR CODING RULES

1. One Telegram chat = one independent WORLD INSTANCE.

2. Telegram is an interface, not the game engine.

3. AI is an interface/helper, not the source of truth.

4. World state can only be changed through validated domain logic.

5. Important state changes happen through EVENTS.

6. Database stores state/history; database is not game logic.

7. Never mix data between WORLD INSTANCES.

8. Player knowledge is not the same as world truth.

9. NPC knowledge is limited.

10. Do not invent new architecture without checking existing architecture.

11. Do not create a giant GameManager/God Object.

12. Prefer small domain modules.

13. Every new feature must answer:
   - What entity changes?
   - What event happens?
   - What state changes?
   - What knowledge changes?
   - What can happen next?

14. Before implementing a large feature:
   - inspect existing code;
   - explain the proposed change;
   - implement only after the structure is clear.

15. Do not rewrite unrelated systems just to add one feature.

16. Write tests for important state transitions.

17. Keep the project simple during MVP.

18. Do not build content before the underlying system works.

19. Never allow AI to directly mutate canonical world state.

20. If existing architecture conflicts with a new idea, stop and explain the conflict instead of silently bypassing the architecture.