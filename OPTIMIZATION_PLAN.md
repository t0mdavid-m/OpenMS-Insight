# Data Send Optimization Plan

## Problem Statement
Currently, data is being sent to Vue components even when it hasn't changed, especially in development mode. This wastes bandwidth and processing time.

## Current Implementation Issues

### 1. Dev Mode Override (bridge.py:223-225)
```python
dev_mode = os.environ.get('SVC_DEV_MODE', 'false').lower() == 'true'
if dev_mode:
    data_changed = True  # Always send data in dev mode
```
This defeats the hash-based optimization entirely.

### 2. Unidirectional Confirmation
Python tracks `_VUE_DATA_RECEIVED_KEY` (a set of component keys), but:
- Never cleared when Vue hot reloads
- Doesn't track WHICH hash Vue has
- Python assumes Vue has data; Vue never confirms

### 3. Race Condition After Hot Reload
1. Python: "Vue received data before" → don't send
2. Vue: (after hot reload) has no data
3. Vue displays nothing or stale data
4. Next render: Python finally notices and sends

## Solution: Bidirectional Hash Confirmation

### Core Principle
Vue echoes back the hash it currently has. Python compares:
- `current_data_hash`: What Python just computed
- `vue_echoed_hash`: What Vue reported having (from last render)

Send data when: `vue_echoed_hash != current_data_hash`

### Data Flow
```
Render 1 (initial):
  Python: vue_echoed_hash=undefined, current_hash="abc"
  → Mismatch! Send data with hash="abc"
  Vue: receives data, stores hash="abc"
  Vue: sends back state with _vueDataHash="abc"
  Python: stores vue_echoed_hash["key"]="abc"

Render 2 (data unchanged):
  Python: vue_echoed_hash="abc", current_hash="abc"
  → Match! Don't send data
  Vue: uses cached data
  Vue: sends back state with _vueDataHash="abc"

Render 3 (Vue hot reloads):
  Vue: loses all data, hash becomes undefined
  Vue: sends back state with _vueDataHash=undefined
  Python: stores vue_echoed_hash["key"]=undefined

Render 4 (after hot reload):
  Python: vue_echoed_hash=undefined, current_hash="abc"
  → Mismatch! Send data
  (Vue recovers)
```

## Implementation Changes

### Phase 1: Vue Echoes Hash

**File: `js-component/src/App.vue`** (line ~58)

Change the state send to include the data hash:
```typescript
// Current:
const plainState = JSON.parse(JSON.stringify(selectionStore.$state))
Streamlit.setComponentValue(plainState)

// New:
const plainState = JSON.parse(JSON.stringify(selectionStore.$state))
plainState._vueDataHash = streamlitDataStore.hash || null
Streamlit.setComponentValue(plainState)
```

### Phase 2: Python Uses Echoed Hash

**File: `rendering/bridge.py`**

1. Add new session state key:
```python
_VUE_ECHOED_HASH_KEY = "_svc_vue_echoed_hashes"  # dict[component_key, hash]
```

2. Update `render_component()` to use Vue's echoed hash:
```python
# Initialize echoed hash tracking
if _VUE_ECHOED_HASH_KEY not in st.session_state:
    st.session_state[_VUE_ECHOED_HASH_KEY] = {}

# Get Vue's last-echoed hash for this component
vue_echoed_hash = st.session_state[_VUE_ECHOED_HASH_KEY].get(key)

# Send data if Vue's hash doesn't match current hash
# This handles: first render, data change, Vue hot reload
data_changed = (vue_echoed_hash != data_hash)

# REMOVE the dev mode override:
# if dev_mode:
#     data_changed = True
```

3. After Vue returns, store its echoed hash:
```python
if result is not None:
    vue_hash = result.get('_vueDataHash')
    st.session_state[_VUE_ECHOED_HASH_KEY][key] = vue_hash

    # Update state and rerun if changed
    if state_manager.update_from_vue(result):
        st.rerun()
```

4. Remove the old `_VUE_DATA_RECEIVED_KEY` tracking (no longer needed).

### Phase 3: Clean Up StateManager

**File: `core/state.py`**

Ensure `update_from_vue()` ignores the `_vueDataHash` key when updating selections:
```python
def update_from_vue(self, vue_state: Dict[str, Any]) -> bool:
    # Skip internal keys
    filtered_state = {
        k: v for k, v in vue_state.items()
        if not k.startswith('_')  # Skip _vueDataHash, etc.
    }
    ...
```

## Edge Cases Handled

| Scenario | vue_echoed_hash | data_hash | Result |
|----------|-----------------|-----------|--------|
| First render | `None` | `"abc"` | Send data |
| Data unchanged | `"abc"` | `"abc"` | Don't send |
| Data changed | `"abc"` | `"xyz"` | Send data |
| Vue hot reload | `None` | `"abc"` | Send data |
| Different component | `None` (new key) | `"abc"` | Send data |

## Benefits

1. **Correct in dev mode**: No more forcing data send on every render
2. **Handles hot reload**: Vue losing data triggers resend automatically
3. **Efficient**: Only sends data when Vue actually needs it
4. **Simple**: No complex bidirectional protocols, just hash comparison

## Testing Plan

1. **Basic test**: Load app, verify data sent once, interact, verify no redundant sends
2. **Hot reload test**: Change Vue code, verify data resent after hot reload
3. **State change test**: Click heatmap, verify only affected components get new data
4. **Zoom test**: Zoom heatmap, verify new resolution level sent
5. **Browser refresh test**: Refresh page, verify data resent

## Performance Metrics

Add timing logs to measure improvement:
- Count of data sends per render
- Bytes transferred per render
- Time spent in data conversion (to_pandas, Arrow serialization)
