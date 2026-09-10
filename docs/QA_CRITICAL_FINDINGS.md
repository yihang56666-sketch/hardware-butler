> ⚠️ SUPERSEDED：本文件为历史 QA 快照，结论可能已过时。以最新 pytest 实测与 PROJECT_PORTFOLIO_AUDIT.md 为准。

# Critical Issues Found by QA Agent

## 🔴 Active Bugs Found

### 1. **test_build_plan.py - API Mismatch** ❌
**Status**: Tests expect old API but code changed

```python
# Tests expect:
plan["backend"]
plan["steps"]

# Code actually returns:
plan["selected_backend"]["backend"]
plan["commands"]
```

**Fix**: Update test assertions

### 2. **test_configure_logging_sets_level - Failing Test** ❌
**Status**: Test fails because handler level is NOTSET not ERROR

**Fix**: Either fix configure_logging() or fix test expectations

### 3. **test_cube_detect.py - Structure Mismatch** ❌
**Status**: Tests expect flat structure but code may be nested

---

## 🚨 Critical Coverage Gaps

### butler_cli.py - **ZERO Coverage** ❌
New CLI has no tests. Need:
- Command parsing tests
- Argument forwarding tests
- Error handling tests

### butler_types.py - **ZERO Coverage** ⚠️
TypedDict definitions have no validation tests

---

## 📊 Test Coverage Summary (QA Agent Report)

| Module | Coverage | Status | Critical Issues |
|--------|----------|--------|-----------------|
| config.py | 85-90% | ✅ Good | Missing error handling |
| logger.py | 60-70% | ⚠️ Partial | **Bug in test, missing file handler tests** |
| cache.py | 80-85% | ✅ Good | Missing concurrency tests |
| safe_io.py | 90-95% | ✅ Excellent | - |
| runtime_context.py | 90% | ✅ Excellent | - |
| document_providers.py | 95% | ✅ Excellent | - |
| **butler_cli.py** | **0%** | ❌ **None** | **No tests at all** |
| **butler_types.py** | **0%** | ⚠️ N/A | No runtime validation |
| build_plan.py | 30% | ❌ **Broken** | **Tests use old API** |
| cube_detect.py | - | ❌ **Broken** | **Tests use wrong structure** |

---

## ⚡ Immediate Action Items

### Priority 1: Fix Broken Tests (TODAY)
1. ✅ Update `test_build_plan.py` API expectations
2. ✅ Fix `test_configure_logging_sets_level`
3. ✅ Update `test_cube_detect.py` structure

### Priority 2: Add Critical Tests (THIS WEEK)
1. ❌ Create `test_butler_cli.py` - **Most critical**
2. ❌ Create `test_butler_types.py`
3. ❌ Add error path tests for all modules

### Priority 3: Improve Quality (ONGOING)
1. Enforce AAA pattern in tests
2. Add edge case tests
3. Add integration tests

---

## 🎯 Target Coverage Goals

After fixes:
- **butler_cli.py**: 0% → 80%
- **logger.py**: 70% → 85%
- **build_plan.py**: 30% → 80%
- **Overall**: 78% → 85%
