# Implementation Plan: 03 TypeScript Analyzer

Depends on spec 01 tasks 1–6 and spec 02 tasks 1 and 6.4 (shared contract and text-reference helper).

- [x] 1. Tree-sitter spike (timebox: 1 hour)
  - Install the three approved packages; parse one `.ts`, one `.tsx`, one `.js` file; print the node types for a function declaration, arrow-function const, class method, import, export, JSX element
  - Correct any node type name in `design.md` that differs from the installed grammar; record the installed versions in `pyproject.toml` as exact pins
  - If prebuilt wheels are not available for the Docker base image, stop and ask the owner
  - _Requirements: 1.1_

- [x] 2. Parser wrapper
  - `parser.py`: grammar per extension, `parse(bytes) -> tree`, `has_error`, iterative cursor walk helper
  - _Requirements: 1.1, 1.5, 8.4_

- [ ] 3. Collect definitions
  - [ ] 3.1 TS-D1 and TS-D2 (function declarations, arrow-function constants), with Span and exported status from an enclosing `export_statement`
    - _Requirements: 1.2, 1.3_
  - [ ] 3.2 TS-D3 (class methods) and TS-D4 (anonymous default exports)
    - _Requirements: 1.2, 1.3_
  - [ ] 3.3 Exported status from `export { }` clauses and CommonJS assignments
    - _Requirements: 3.7_
  - [ ] 3.4 Unit tests, one per TS-D rule, plus "nested function ignored" and "parse-error file yields no definitions"
    - _Requirements: 1.2–1.5_

- [ ] 4. Collect references
  - [ ] 4.1 TS-R1 to TS-R4
    - _Requirements: 2.1, 3.1_
  - [ ] 4.2 TS-R5 (JSX names) and TS-R6 (import/export specifier names)
    - _Requirements: 3.1, 4.2_
  - [ ] 4.3 Token fallback for parse-error files; repo-wide `ReferenceIndex`
    - _Requirements: 1.5_
  - [ ] 4.4 Unit tests, one per TS-R rule
    - _Requirements: 4.2, 4.3_

- [ ] 5. Join: non-exported functions
  - Same-file rule for ES modules (TS-S1, TS-S5); `SCRIPT_GLOBAL` path for Scripts; method rule: TS-S4 class families, unresolved member accesses by name; snippets; `test_coverage`
  - Arity rule TS-A1 and flag `ARITY_MISMATCH` (`.ts`/`.tsx` only), with unit tests for too many arguments, too few, optional and default parameters, rest parameter, spread call skipped, `.js` call skipped
  - Wire `analyse_typescript` into the CLI and run on `samples/haunted-repo`
  - _Requirements: 2.1–2.4, 6.1, 9.1_

- [ ] 6. Join: exported functions
  - [ ] 6.1 `exports.py`: collect import/re-export/require/dynamic-import specifiers into `SpecifierIndex`
    - _Requirements: 3.3, 3.5_
  - [ ] 6.2 `resolve.py`: specifier resolution (relative exact, workspace package, external package, TS-R7 suffix for aliases, unresolved fallback), with unit tests for `./`, `../`, `@/`, `/index`, extension, bare-package and workspace-package cases
    - _Requirements: 3.1, 3.1a, 3.3_
  - [ ] 6.3 Named-export decision with TS-S2 and TS-S3 (named, default, namespace and `require` bindings), re-export following (depth 5), `EXPORTED` flag; `DYNAMIC_IMPORT` and `reexport` callers
    - _Requirements: 3.1, 3.1a, 3.2, 3.5, 3.6, 3.7_
  - [ ] 6.5 Unit tests, one per TS-S rule, plus "two files export the same name, one imported" and "barrel `export *` keeps the target alive"
    - _Requirements: 3.1, 3.1b_
  - [ ] 6.4 `PackageIndex` from `package.json` files; `LIBRARY_API` (TS-F2)
    - _Requirements: 3.4_

- [ ] 7. Exemptions
  - [ ] 7.1 TS-E1 (Next.js) and TS-E2 (other route modules)
    - _Requirements: 4.1_
  - [ ] 7.2 TS-E3 (entry files), TS-E4 (framework methods), TS-E5 (decorators), TS-E6 (stubs)
    - _Requirements: 4.1_
  - [ ] 7.3 One unit test per TS-E rule, named after the rule ID
    - _Requirements: 4.4_

- [ ] 8. Flags and weak references
  - TS-F5 string and template literals + Text-reference files; TS-F6; TS-F7; TS-F8; caller cap
  - One unit test per flag
  - _Requirements: 5.1–5.5_

- [ ] 9. Dead imports
  - [ ] 9.1 `imports.py`: ImportBindings (default, named, namespace, type) with statement line range
    - _Requirements: 7.1, 7.3_
  - [ ] 9.2 Same-file usage check; exclusions; `PARTIAL_STATEMENT`
    - _Requirements: 7.1, 7.2, 7.4, 7.5_
  - [ ] 9.3 Unit tests: unused named, unused default, unused type import, `React` in `.tsx` kept, side-effect import kept, re-exported import kept
    - _Requirements: 7.1, 7.2_

- [ ] 10. Robustness and property tests
  - [ ] 10.1 Per-file exception containment, deadline, sorted output
    - _Requirements: 8.1–8.3_
  - [ ] 10.2 `ts_repo()` strategy; P1-ts, P2-ts
    - _Requirements: 8.1, 1.2_
  - [ ] 10.3 P3-ts, P7-ts, P5-ts, P13-ts, P4a-ts, P24-ts, P25-ts
    - _Requirements: 2.1, 3.1, 3.1a, 3.1b, 3.7, 7.1, 8.2_

- [ ] 11. TypeScript half of the accuracy gate
  - Compare Candidates on both sample repos with the TypeScript entries of `expected.json` (names, kinds, flags)
  - _Requirements: 2.1, 3.2, 4.4, 7.1_

- [ ]* 12. (P1, needs owner approval) Zombie tests
  - _Requirements: 10.1_
