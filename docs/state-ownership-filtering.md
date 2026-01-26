# State Ownership Filtering (Removed Feature)

This document describes the state ownership filtering mechanism that was implemented to prevent race conditions in multi-component state synchronization but was subsequently removed during cleanup. This documentation is preserved for potential future reimplementation if needed.

## Problem Statement

When multiple Vue components run in parallel within a single Streamlit page, each component independently sends its selection state back to Python via `Streamlit.setComponentValue()`. This creates a race condition:

1. Component A (e.g., spectrum table) has state: `{spectrum: 5, peak: null, counter: 10}`
2. Component B (e.g., peak table) has state: `{spectrum: 5, peak: 100, counter: 11}`
3. User clicks on Component A to select spectrum 6
4. Component A sends: `{spectrum: 6, peak: null, counter: 12}` (its local view)
5. This overwrites Component B's `peak: 100` with `peak: null`

The issue is that each component only "owns" certain state keys but sends the full state object.

## Algorithm Description

State ownership filtering addresses this by:

1. **Defining Ownership**: Each component declares which state keys it "owns":
   - `interactivity` keys: The identifiers this component sets on user interaction
   - `paginationIdentifier`: For tables with server-side pagination

2. **Filtering State**: When sending state to Python:
   - Only include keys the component owns
   - Always include metadata keys (`id`, `counter`)
   - Always include `_` prefixed internal keys (`_vueDataHash`, `_requestData`, etc.)

3. **Merging on Python Side**: Python accepts updates only for owned keys, preserving other components' state.

## Implementation Details

### Vue Side (App.vue)

```typescript
const sendStateToStreamlit = () => {
  // Get component args to determine owned keys
  const components = streamlitDataStore.args?.components
  const componentArgs = components && components.length > 0 && components[0].length > 0
    ? components[0][0].componentArgs
    : undefined

  // Build set of keys this component owns
  const ownedKeys = new Set<string>()
  if (componentArgs) {
    // Interactivity keys - identifiers this component SETS on user interaction
    if ('interactivity' in componentArgs && componentArgs.interactivity) {
      for (const identifier of Object.keys(componentArgs.interactivity)) {
        ownedKeys.add(identifier)
      }
    }
    // Pagination key - only for tables with server-side pagination
    if ('paginationIdentifier' in componentArgs && componentArgs.paginationIdentifier) {
      ownedKeys.add(componentArgs.paginationIdentifier)
    }
  }

  // Build filtered state: metadata + owned keys only
  const rawState = selectionStore.$state
  const filteredState: Record<string, unknown> = {
    id: rawState.id,
    counter: rawState.counter,
  }

  // Add only owned selection keys
  for (const key of ownedKeys) {
    if (key in rawState) {
      filteredState[key] = rawState[key]
    }
  }

  // ... rest of send logic
  Streamlit.setComponentValue(plainState)
}
```

### Python Side (bridge.py)

```python
# Build set of keys this component owns
owned_keys = {"id", "counter"}  # Metadata always accepted

# Interactivity keys - identifiers this component SETS on user interaction
interactivity = getattr(component, "_interactivity", None) or {}
owned_keys.update(interactivity.keys())

# Pagination key - for tables with server-side pagination
pagination_id = component_args.get("paginationIdentifier")
if pagination_id:
    owned_keys.add(pagination_id)

# Filter result to owned keys (preserve _ prefixed metadata)
if result:
    filtered_result = {
        k: v
        for k, v in result.items()
        if k.startswith("_") or k in owned_keys
    }
else:
    filtered_result = result

state_changed = state_manager.update_from_vue(filtered_result)
```

## Data Flow Diagram

```
User clicks row in Table A (spectrum)
            │
            ▼
┌─────────────────────────────────────┐
│ Table A: Vue Component              │
│ owns: {spectrum}                    │
│ interactivity: {spectrum: 'scan_id'}│
└─────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────┐
│ App.vue: sendStateToStreamlit()     │
│ 1. Get componentArgs                │
│ 2. Build ownedKeys = {spectrum}     │
│ 3. Filter state to owned keys       │
│ 4. Send: {spectrum: 6, counter: 12} │
│    NOT: {spectrum: 6, peak: null}   │
└─────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────┐
│ bridge.py: render_component()       │
│ 1. Build owned_keys = {spectrum}    │
│ 2. Filter result to owned keys      │
│ 3. update_from_vue(filtered)        │
│ 4. Python state preserves peak=100  │
└─────────────────────────────────────┘
```

## Edge Cases

1. **Initial State**: On first render, components have no state yet. The `id` and `counter` keys are always sent.

2. **Session Change**: When `id` changes (new session), all state is cleared and replaced.

3. **Counter Conflicts**: The counter-based resolution in `StateManager.update_from_vue()` handles cases where Vue sends older state than Python has.

4. **Multiple Interactivity Keys**: A component can own multiple keys if it has multiple `interactivity` entries.

## Why It Was Removed

The implementation was removed because:

1. **Complexity**: Added significant code to both Vue and Python sides
2. **Testing Overhead**: Required careful testing of multi-component scenarios
3. **Single-Component Pages**: Most current use cases have one component per page
4. **Counter-Based Resolution**: The existing counter-based conflict resolution already handles most race conditions

## Potential Reimplementation

If multi-component race conditions become a problem in future deployments:

1. Re-add the `ownedKeys` logic to `App.vue`'s `sendStateToStreamlit()`
2. Re-add the `owned_keys` filtering to `bridge.py`'s `render_component()`
3. Add tests for multi-component state sync scenarios
4. Consider adding this as an optional feature (e.g., `enable_state_ownership: bool`)

## Related Files

- `js-component/src/App.vue` - Vue state sending logic
- `openms_insight/rendering/bridge.py` - Python state receiving logic
- `openms_insight/core/state.py` - StateManager with counter-based resolution
