import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

import deobfuscator
import trace_to_lua


class CaptureTests(unittest.TestCase):
    def deobfuscate(self, source, suffix=".lua"):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        sample = Path(directory.name) / ("sample" + suffix)
        sample.write_text(source, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            result = deobfuscator.deobfuscate_file(str(sample))
        output = sample.with_name(sample.name + ".deobf.lua")
        self.assertTrue(output.exists(), "deobfuscation produced no output")
        report = sample.with_name(sample.name + ".report.txt").read_text()
        self.assertNotIn("RUNTIME ERROR", report)
        self.assertNotIn("COMPILE ERROR", report)
        return result, output, report

    def test_plain_source_without_string_table_preserves_print_arguments(self):
        _, output, _ = self.deobfuscate('print("line\\nnext", 42, false, nil, "after")')
        process = subprocess.run(
            [deobfuscator.get_lua_executable(), str(output)], capture_output=True, check=True
        )
        self.assertEqual(process.stdout, b"line\nnext\t42\tfalse\tnil\tafter\n")

    def test_decrypted_cache_captures_unprinted_binary_string(self):
        _, output, report = self.deobfuscate(
            'local cache = {}; local strings = setmetatable({}, {__index = cache}); '
            'cache[123] = string.char(0, 255) .. "secret"; '
            'assert(strings[123] ~= ""); print("done")'
        )
        self.assertIn('"\\000\\255secret"', report)
        self.assertIn('"\\000\\255secret"', output.read_text())

    def test_mixed_constants_retain_types_and_false_values(self):
        _, _, report = self.deobfuscate(
            'local constants = {"text", 42, false, true, -3.25}; print(constants[1])'
        )
        constants = report.split("--- CONSTANTS ---\n", 1)[1]
        self.assertIn('[1] = "text"', constants)
        self.assertIn('[2] = 42', constants)
        self.assertIn('[3] = false', constants)
        self.assertIn('[4] = true', constants)
        self.assertIn('[5] = -3.25', constants)

    def test_luau_normalization_preserves_strings_and_expression_precedence(self):
        source = 'local n = 2\nn *= 3 + 4\nprint("literal += text", n)'
        rewritten = deobfuscator.normalize_luau_syntax(source)
        self.assertIn('"literal += text"', rewritten)
        _, output, _ = self.deobfuscate(source, ".luau")
        process = subprocess.run(
            [deobfuscator.get_lua_executable(), str(output)], capture_output=True, check=True
        )
        self.assertEqual(process.stdout, b"literal += text\t14\n")

    def test_failed_chunk_is_reported_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            sample = Path(directory) / "broken.lua"
            sample.write_text('error("fixture failure")')
            with contextlib.redirect_stdout(io.StringIO()):
                result = deobfuscator.deobfuscate_file(str(sample))
            self.assertFalse(result)
            self.assertIn("RUNTIME ERROR", sample.with_name("broken.lua.report.txt").read_text())

    def test_variable_resolution_does_not_rewrite_string_contents(self):
        self.assertEqual(
            trace_to_lua.resolve_vars('print(trace_1, "trace_1 _v1")', {"trace_1": "Players"}),
            'print(Players, "trace_1 _v1")',
        )

    def test_trace_with_invalid_child_identifier_still_compiles(self):
        _, output, _ = self.deobfuscate(
            'local item = game:WaitForChild("item with spaces"); '
            'print(item, "trace_1"); item.Name = "function: abcdefabcdef"'
        )
        process = subprocess.run(
            [deobfuscator.get_lua_executable(), "-e",
             "assert(loadfile(" + deobfuscator.lua_string(str(output)) + "))"],
            capture_output=True,
        )
        self.assertEqual(process.returncode, 0, process.stderr.decode())

    def test_argument_split_handles_escaped_quotes_and_nested_tables(self):
        arguments = r'"quoted\",comma", {["a,b"] = {1, 2}}, 42'
        self.assertEqual(trace_to_lua.smart_split_args(arguments),
                         [r'"quoted\",comma"', ' {["a,b"] = {1, 2}}', " 42"])

    def test_callback_failure_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            sample = Path(directory) / "callback.lua"
            sample.write_text('game.Event:Connect(function() error("callback failure") end)')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(deobfuscator.deobfuscate_file(str(sample)))

    def test_repeated_calls_remain_finite(self):
        _, output, _ = self.deobfuscate('for i = 1, 4 do game:GetService("Players") end')
        self.assertNotIn("while true", output.read_text())
        self.assertEqual(output.read_text().count('game:GetService("Players")'), 4)

    def test_compound_index_expression_is_evaluated_once(self):
        source = (
            'local values = {10, 20}; local count = 0; '
            'local function index() count = count + 1; return count end; '
            'values[index()] += 1; print(values[1], values[2], count)'
        )
        _, output, _ = self.deobfuscate(source, ".luau")
        self.assertEqual(subprocess.check_output([deobfuscator.get_lua_executable(), str(output)]),
                         b"11\t20\t1\n")

    def test_compound_multiline_rhs_keeps_precedence(self):
        _, output, _ = self.deobfuscate('local n = 2\nn *= 3\n + 4\nprint(n)', ".luau")
        self.assertEqual(subprocess.check_output([deobfuscator.get_lua_executable(), str(output)]), b"14\n")

    def test_repeated_global_and_shared_writes_are_captured(self):
        _, output, report = self.deobfuscate(
            'message="old"; message="new"; shared.message="shared-secret"; '
            'message=nil; print(message, shared.message)'
        )
        self.assertIn('message = "new"', output.read_text())
        self.assertIn('shared["message"] = "shared-secret"', output.read_text())
        self.assertIn('"shared-secret"', report)
        self.assertIn('message = nil', output.read_text())

    def test_generated_local_names_do_not_shadow_globals(self):
        _, output, _ = self.deobfuscate('local item = game:WaitForChild("print"); print(item); print("hello")')
        self.assertNotIn("local print =", output.read_text())

    def test_variable_resolution_preserves_member_keys(self):
        self.assertEqual(trace_to_lua.resolve_vars('game.trace_1 = trace_1', {"trace_1": "Players"}),
                         'game.trace_1 = Players')

    def test_nested_callbacks_keep_distinct_argument_names(self):
        _, output, _ = self.deobfuscate(
            'game.Event:Connect(function(a) '
            'game.Other:Connect(function(b) print(a, b) end) end)'
        )
        self.assertIn("print(callback1_arg1, callback2_arg1)", output.read_text())

    def test_multiple_callbacks_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            sample = Path(directory) / "callbacks.lua"
            sample.write_text('game.Test(function() print("first") end, function() print("second") end)')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(deobfuscator.deobfuscate_file(str(sample)))
            self.assertIn("multiple callback arguments are unsupported",
                          Path(str(sample) + ".report.txt").read_text())

    def test_diagnostic_constants_do_not_shadow_source_globals(self):
        _, output, _ = self.deobfuscate('Constants = "source-global"; print(Constants)')
        stdout, stderr, code = deobfuscator.run_chunk(output.read_text())
        self.assertEqual(code, 0, stderr)
        self.assertIn('SET GLOBAL --> Constants = "source-global"', stdout)

    def test_proxy_globals_preserve_raw_access(self):
        _, _, report = self.deobfuscate(
            'rawset(_G, "message", "raw-secret"); '
            'assert(rawget(_G, "message") == "raw-secret"); '
            'rawset(shared, "message", "shared-raw"); '
            'assert(rawget(shared, "message") == "shared-raw")'
        )
        self.assertIn('"raw-secret"', report)
        self.assertIn('"shared-raw"', report)

    def test_parenthesized_compound_lhs_after_keyword(self):
        _, output, _ = self.deobfuscate(
            'local t={x=1}; if true then (t).x += 2 end; print(t.x)', ".luau"
        )
        self.assertEqual(subprocess.check_output([deobfuscator.get_lua_executable(), str(output)]), b"3\n")

    def test_next_visits_tracked_shared_values(self):
        _, _, report = self.deobfuscate(
            'shared.x="secret"; local key, value = next(shared); '
            'assert(key == "x" and value == "secret"); print(key, value)'
        )
        self.assertIn('print("x", "secret")', report)


if __name__ == "__main__":
    unittest.main()
