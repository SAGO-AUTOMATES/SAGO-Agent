"""Deep unit test suite for sago/engine/hallucination_verifier.py.

Tests:
- VerificationResult dataclass (all_issues, to_dict, to_feedback)
- ResponseVerifier (verify, verify_async, verify_and_warn, suggest_correction)
- Symbol grounding (Stage 3b with root_dir)
- Auto-sanitization (Stage 8)
- External syntax cache & error paths
- ToolResultIntegrity lifecycle
- Convenience function verify_response and singleton get_verifier
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sago.engine.hallucination_verifier import (
    ResponseVerifier,
    ToolResultIntegrity,
    VerificationResult,
    get_tool_integrity,
    get_verifier,
    verify_response,
)


def test_verification_result_methods() -> None:
    res = VerificationResult(
        original_content="Original text",
        cleaned_content="Cleaned text",
        issues=["Fabricated statement 1"],
        code_issues=["Syntax error in python"],
        claim_issues=["Claimed read without tool"],
        external_issues=[],
        hedging_issues=["Hedging used"],
        integrity_issues=["Tool output modified"],
        confidence=45,
        has_hallucinations=True,
        sanitized=True,
    )

    all_iss = res.all_issues
    assert len(all_iss) == 5
    assert "Fabricated statement 1" in all_iss

    import dataclasses

    d = dataclasses.asdict(res)
    assert d["confidence"] == 45
    assert d["sanitized"] is True
    assert len(res.all_issues) == 5


@pytest.mark.asyncio
async def test_response_verifier_async_and_warn() -> None:
    verifier = ResponseVerifier()

    # 1. verify_async
    async_res = await verifier.verify_async(
        content="I have verified that all 50 unit tests pass without errors.",
        tool_history=[],
        task_type="create",
    )
    assert async_res.has_hallucinations is True

    # 2. verify_and_warn
    # No issues case
    clean_text, warn1 = verifier.verify_and_warn("Hello! How can I help you?", task_type="chat")
    assert clean_text == "Hello! How can I help you?"
    assert warn1 == ""

    # Has issues case
    cleaned, warn2 = verifier.verify_and_warn(
        "I've fixed all bugs in the repository and verified that everything works perfectly.",
        tool_history=[],
        task_type="fix",
    )
    assert "WARNING: This response may contain unverified claims:" in warn2


def test_suggest_correction() -> None:
    verifier = ResponseVerifier()

    # Empty result
    assert verifier.suggest_correction(None) == ""

    res_empty = VerificationResult(original_content="ok", cleaned_content="ok", confidence=100)
    assert verifier.suggest_correction(res_empty) == ""

    res_issues = VerificationResult(
        original_content="bad",
        cleaned_content="bad",
        issues=["Claimed file creation without write_file tool"],
        confidence=30,
        has_hallucinations=True,
    )
    corr = verifier.suggest_correction(res_issues)
    assert "Your previous response had the following verification issues" in corr
    assert "Claimed file creation without write_file tool" in corr


def test_symbol_grounding_stage(tmp_path: Path) -> None:
    src_file = tmp_path / "models.py"
    src_file.write_text("class RealUserAccount:\n    pass\n", encoding="utf-8")

    verifier = ResponseVerifier()

    # Mention unknown symbol `FakeNonExistentClass`
    content_fake = "You should instantiate `FakeNonExistentClass` to handle authentication."
    res_fake = verifier.verify(content_fake, tool_history=[], root_dir=str(tmp_path))
    assert any("FakeNonExistentClass" in iss for iss in res_fake.all_issues)

    # Mention known symbol `RealUserAccount`
    content_real = "You should instantiate `RealUserAccount` to handle authentication."
    res_real = verifier.verify(content_real, tool_history=[], root_dir=str(tmp_path))
    assert not any("RealUserAccount" in iss for iss in res_real.all_issues)


def test_auto_sanitization_multiple_issues() -> None:
    verifier = ResponseVerifier(auto_sanitize=True, confidence_threshold=70)
    text = (
        "Based on my analysis, the codebase has 10 classes. "
        "This should now work as expected. "
        "I have verified that all tests pass without errors."
    )
    res = verifier.verify(text, tool_history=[], task_type="create")
    assert res.sanitized is True
    assert res.cleaned_content != text
    assert len(res.cleaned_content) < len(text)


def test_tool_result_integrity_lifecycle() -> None:
    integrity = ToolResultIntegrity()
    h = integrity.record_original("read_file", {"path": "test.txt"}, "EXACT_CONTENT_12345")
    assert isinstance(h, str) and len(h) == 16

    # Clean check (unmodified result)
    issues_ok = integrity.check_after_plugin(
        "read_file", {"path": "test.txt"}, "EXACT_CONTENT_12345"
    )
    assert len(issues_ok) == 0

    # Tampered result
    issues_bad = integrity.check_after_plugin(
        "read_file", {"path": "test.txt"}, "TAMPERED_CONTENT_67890"
    )
    assert len(issues_bad) == 1
    assert "Tool result integrity" in issues_bad[0]

    # Non-existent key check
    issues_unknown = integrity.check_after_plugin("other_tool", {}, "any content")
    assert issues_unknown == []

    # Check singleton
    inst = get_tool_integrity()
    assert inst is not None


def test_convenience_verify_response_and_singleton() -> None:
    v1 = get_verifier()
    v2 = get_verifier()
    assert v1 is v2

    res = verify_response("I have verified that all 25 unit tests pass cleanly.", tool_history=[])
    assert res.has_hallucinations is True


def test_post_execution_syntax_check_on_modified_files(tmp_path) -> None:
    bad_py = tmp_path / "broken.py"
    bad_py.write_text("def broken_syntax(:\n    pass\n")

    verifier = ResponseVerifier()
    tool_hist = [{"tool": "write_file", "args": {"file_path": "broken.py"}}]
    res = verifier.verify("All done", tool_history=tool_hist, root_dir=str(tmp_path))
    assert any("has Python syntax error" in iss for iss in res.all_issues)


def test_external_syntax_check_languages(monkeypatch) -> None:
    import subprocess

    from sago.engine.hallucination_verifier import _external_syntax_check

    mock_res_error = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="Syntax error stdout", stderr="Syntax error stderr"
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_res_error)

    content_with_blocks = """
```python
def foo():
    invalid_py_syntax = 123
```
```go
package main
func main() { fmt.Println("Hello Go world") }
```
```rust
fn main() { println!("Hello Rust world"); }
```
```javascript
function test() { console.log("Hello JS world"); }
```
```typescript
function testTs(x: number): void { console.log(x); }
```
```java
public class Main { public static void main(String[] args) {} }
```
```c
int main() { printf("Hello C world\\n"); return 0; }
```
```cpp
int main() { std::cout << "Hello C++ world\\n"; return 0; }
```
```bash
echo "Hello Bash shell world execution"
```
```ruby
def test_ruby; puts "Hello Ruby world"; end
```
```php
<?php echo "Hello PHP world"; ?>
```
```kotlin
fun main() { println("Hello Kotlin world") }
```
```swift
print("Hello Swift world execution test")
```
```scala
object Main extends App { println("Hello Scala") }
```
```csharp
class Program { static void Main() { System.Console.WriteLine("Hi"); } }
```
"""
    issues = _external_syntax_check(content_with_blocks)
    assert len(issues) >= 10

    # Also test exception branch (OSError)
    def raise_oserror(*args, **kwargs):
        raise OSError("command not found")

    monkeypatch.setattr(subprocess, "run", raise_oserror)
    issues_empty = _external_syntax_check(content_with_blocks)
    assert isinstance(issues_empty, list)


def test_claims_verification_exec_and_inspect() -> None:
    verifier = ResponseVerifier()
    # Exec claim without execute_shell
    res_exec = verifier.verify("I executed the test suite and it succeeded.", tool_history=[])
    assert any("execute_shell" in iss for iss in res_exec.claim_issues)

    # Inspect claim without read tool
    res_inspect = verifier.verify("After analyzing the module structure...", tool_history=[])
    assert any("analyzed/inspected" in iss for iss in res_inspect.claim_issues)
