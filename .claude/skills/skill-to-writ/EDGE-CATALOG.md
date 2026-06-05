# Edge catalog

When to use each edge type. Edges are directed: source -> target.

## Structural edges

**CONTAINS**: Playbook -> Phase. Phase is a structural member of the playbook. Every Phase must have exactly one incoming CONTAINS from its parent.

**ATTACHED_TO**: Rationalization -> Skill/Playbook/Rule. The rationalization is about the target; surfaces when the target is retrieved.

## Prerequisite and ordering edges

**DEPENDS_ON**: Any -> Any. Target is a prerequisite for source. Source assumes target's constraints are already met. Use when one rule only makes sense after another is established.

**PRECEDES**: Rule/Skill -> Rule/Skill. Source must fire or be satisfied before target. Use for ordered execution, not conceptual dependency (that is DEPENDS_ON).

## Teaching and enforcement edges

**TEACHES**: Skill/Playbook -> Rule/Technique. Source teaches the enforcement or application of target. Use when a skill or playbook exists to instruct on a rule.

**GATES**: Rule -> Skill/Playbook. Rule mechanically enforces the target's discipline. Use when there is a concrete enforcement mechanism (hook, validator, gate check).

**DEMONSTRATES**: WorkedExample/ForbiddenResponse/Technique -> Skill/Rule. Source demonstrates target's discipline in practice. Use when a technique or example shows a rule being applied.

## Opposition edges

**COUNTERS**: AntiPattern/Rationalization -> Skill/Playbook/Rule. Source is the failure mode; target is what fixes or prevents it. AntiPattern nodes should have COUNTERS edges to every node listed in their `counter_nodes` field.

**CONFLICTS_WITH**: Any -> Any. Source and target are incompatible; applying both creates contradiction. Rare. Use only for genuine mutual exclusion.

## Relationship edges

**SUPPLEMENTS**: Rule -> Rule. Source adds detail or a special case to target. Use when one rule extends another without replacing it.

**SUPERSEDES**: Any -> Any. Source replaces target. Target should be deprecated. Use when a rule is an improved version of another.

**RELATED_TO**: Any -> Any. Thematic connection. Weakest edge type. Use sparingly; prefer a more specific edge type when one fits.

## Testing edges

**PRESSURE_TESTS**: PressureScenario -> Rule/Skill/Playbook. Scenario tests compliance with target. Use when creating test cases for a rule.

## Dispatching edges

**DISPATCHES**: Playbook/Skill -> SubagentRole/Technique. Target is dispatched as a sub-invocation of source. Use when a playbook delegates work to a technique or role.

## Edge inference heuristics

When decomposing a skill into nodes, these patterns reliably produce edges:

- Rule that forbids X + AntiPattern that names X -> AntiPattern COUNTERS Rule
- Playbook with steps -> Playbook CONTAINS Phase (one per step)
- Playbook that uses technique -> Playbook DISPATCHES Technique
- Technique that shows a rule in practice -> Technique DEMONSTRATES Rule
- Rule that depends on another being understood first -> Rule DEPENDS_ON Rule
- Ordered sequence of rules -> Rule PRECEDES Rule
- Rule that extends a more general rule -> Rule SUPPLEMENTS Rule
