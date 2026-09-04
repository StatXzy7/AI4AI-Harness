{
 "unit": "D_glm_s1.json",
 "rule": "earliest complete finish, provable order; NEVER K_admitted",
 "external_mtime": 1788509346.6320536,
 "repo_mtime": 1788504615.4178584,
 "note": "external at 16:05 recovery manifest: 059a410001326ed3; external now: 26d7cd35489a65ca; EXTERNAL WAS REWRITTEN AFTER RECOVERY (later finish)",
 "versions": {
  "repo": {
   "builder": "glm",
   "model": "GLM-5.3",
   "arm": "D",
   "seed": 1,
   "gate": true,
   "forced": true,
   "raw_attempts_per_slot": 3,
   "n_slots": 8,
   "K_admitted": 2,
   "raw_total": 22,
   "R_artifact": 0.0909,
   "R_contract": 0.0909,
   "R_fidelity": 1.0,
   "p_neutral_valid": 0.0909,
   "p_mechanism_pass": 0.0909,
   "results": [
    {
     "harness": "p2_D_glm_s1_repair",
     "arm": "D",
     "strategy": "repair",
     "seed": 1,
     "admitted": true,
     "admitted_attempt": 2,
     "contract": null,
     "n_raw": 3,
     "n_neutral_valid": 1,
     "n_contract_valid": 1,
     "n_mechanism_pass": 1,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "neutral_detail": "SyntaxError: unterminated string literal (detected at line 15) (p2_D_glm_s1_repair.py, line 15)",
       "secs": 37.3
      },
      {
       "attempt": 1,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "neutral_detail": "SyntaxError: unterminated string literal (detected at line 65) (p2_D_glm_s1_repair.py, line 65)",
       "secs": 138.0
      },
      {
       "attempt": 2,
       "neutral_valid": true,
       "mechanism_pass": true,
       "truncated": false,
       "neutral_detail": "neutral-valid (89 chars)",
       "mechanism_detail": {
        "verdict": "PASS",
        "scenario": "repair"
       },
       "secs": 86.6
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_vote3",
     "arm": "D",
     "strategy": "vote3",
     "seed": 1,
     "admitted": false,
     "admitted_attempt": null,
     "contract": null,
     "n_raw": 3,
     "n_neutral_valid": 0,
     "n_contract_valid": 0,
     "n_mechanism_pass": 0,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "neutral_detail": "SyntaxError: unterminated string literal (detected at line 35) (p2_D_glm_s1_vote3.py, line 35)",
       "secs": 286.6
      },
      {
       "attempt": 1,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": true,
       "neutral_detail": "AttributeError: 'P2P2DGlmS1Vote3' object has no attribute '_build_prompt'",
       "secs": 445.9
      },
      {
       "attempt": 2,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "neutral_detail": "SyntaxError: unterminated string literal (detected at line 31) (p2_D_glm_s1_vote3.py, line 31)",
       "secs": 127.5
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_schema_link",
     "arm": "D",
     "strategy": "schema_link",
     "seed": 1,
     "admitted": false,
     "admitted_attempt": null,
     "contract": null,
     "n_raw": 3,
     "n_neutral_valid": 0,
     "n_contract_valid": 0,
     "n_mechanism_pass": 0,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 433.0
      },
      {
       "attempt": 1,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 455.2
      },
      {
       "attempt": 2,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 278.2
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_hint_guard",
     "arm": "D",
     "strategy": "hint_guard",
     "seed": 1,
     "admitted": false,
     "admitted_attempt": null,
     "contract": null,
     "n_raw": 3,
     "n_neutral_valid": 0,
     "n_contract_valid": 0,
     "n_mechanism_pass": 0,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 221.2
      },
      {
       "attempt": 1,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 290.5
      },
      {
       "attempt": 2,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 226.4
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_two_view",
     "arm": "D",
     "strategy": "two_view",
     "seed": 1,
     "admitted": true,
     "admitted_attempt": 0,
     "contract": null,
     "n_raw": 1,
     "n_neutral_valid": 1,
     "n_contract_valid": 1,
     "n_mechanism_pass": 1,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": true,
       "mechanism_pass": true,
       "truncated": false,
       "neutral_detail": "neutral-valid (89 chars)",
       "mechanism_detail": {
        "verdict": "PASS",
        "scenario": "vote2"
       },
       "secs": 118.1
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_decompose",
     "arm": "D",
     "strategy": "decompose",
     "seed": 1,
     "admitted": false,
     "admitted_attempt": null,
     "contract": null,
     "n_raw": 3,
     "n_neutral_valid": 0,
     "n_contract_valid": 0,
     "n_mechanism_pass": 0,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 310.8
      },
      {
       "attempt": 1,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 289.1
      },
      {
       "attempt": 2,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": true,
       "neutral_detail": "SyntaxError: unterminated triple-quoted string literal (detected at line 1) (p2_D_glm_s1_decompose.py, line 1)",
       "secs": 235.4
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_error_classify",
     "arm": "D",
     "strategy": "error_classify",
     "seed": 1,
     "admitted": false,
     "admitted_attempt": null,
     "contract": null,
     "n_raw": 3,
     "n_neutral_valid": 0,
     "n_contract_valid": 0,
     "n_mechanism_pass": 0,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 311.6
      },
      {
       "attempt": 1,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 204.4
      },
      {
       "attempt": 2,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 289.9
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_format_guard",
     "arm": "D",
     "strategy": "format_guard",
     "seed": 1,
     "admitted": false,
     "admitted_attempt": null,
     "contract": null,
     "n_raw": 3,
     "n_neutral_valid": 0,
     "n_contract_valid": 0,
     "n_mechanism_pass": 0,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 246.7
      },
      {
       "attempt": 1,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 332.9
      },
      {
       "attempt": 2,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "neutral_detail": "SyntaxError: unterminated triple-quoted string literal (detected at line 1) (p2_D_glm_s1_format_guard.py, line 1)",
       "secs": 292.9
      }
     ]
    }
   ],
   "_src": "repo (committed 48fa0a6)"
  },
  "external": {
   "builder": "glm",
   "model": "GLM-5.3",
   "arm": "D",
   "seed": 1,
   "gate": true,
   "forced": true,
   "raw_attempts_per_slot": 3,
   "n_slots": 8,
   "K_admitted": 3,
   "raw_total": 20,
   "R_artifact": 0.15,
   "R_contract": 0.15,
   "R_fidelity": 1.0,
   "p_neutral_valid": 0.15,
   "p_mechanism_pass": 0.15,
   "results": [
    {
     "harness": "p2_D_glm_s1_repair",
     "arm": "D",
     "strategy": "repair",
     "seed": 1,
     "admitted": true,
     "admitted_attempt": 1,
     "contract": null,
     "n_raw": 2,
     "n_neutral_valid": 1,
     "n_contract_valid": 1,
     "n_mechanism_pass": 1,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "neutral_detail": "SyntaxError: unterminated string literal (detected at line 28) (p2_D_glm_s1_repair.py, line 28)",
       "secs": 54.3
      },
      {
       "attempt": 1,
       "neutral_valid": true,
       "mechanism_pass": true,
       "truncated": false,
       "neutral_detail": "neutral-valid (88 chars)",
       "mechanism_detail": {
        "verdict": "PASS",
        "scenario": "repair"
       },
       "secs": 48.1
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_vote3",
     "arm": "D",
     "strategy": "vote3",
     "seed": 1,
     "admitted": true,
     "admitted_attempt": 1,
     "contract": null,
     "n_raw": 2,
     "n_neutral_valid": 1,
     "n_contract_valid": 1,
     "n_mechanism_pass": 1,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "neutral_detail": "SyntaxError: unterminated string literal (detected at line 36) (p2_D_glm_s1_vote3.py, line 36)",
       "secs": 310.6
      },
      {
       "attempt": 1,
       "neutral_valid": true,
       "mechanism_pass": true,
       "truncated": false,
       "neutral_detail": "neutral-valid (88 chars)",
       "mechanism_detail": {
        "verdict": "PASS",
        "scenario": "vote"
       },
       "secs": 77.1
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_schema_link",
     "arm": "D",
     "strategy": "schema_link",
     "seed": 1,
     "admitted": false,
     "admitted_attempt": null,
     "contract": null,
     "n_raw": 3,
     "n_neutral_valid": 0,
     "n_contract_valid": 0,
     "n_mechanism_pass": 0,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 253.7
      },
      {
       "attempt": 1,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 240.0
      },
      {
       "attempt": 2,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 280.8
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_hint_guard",
     "arm": "D",
     "strategy": "hint_guard",
     "seed": 1,
     "admitted": false,
     "admitted_attempt": null,
     "contract": null,
     "n_raw": 3,
     "n_neutral_valid": 0,
     "n_contract_valid": 0,
     "n_mechanism_pass": 0,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 282.6
      },
      {
       "attempt": 1,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 383.0
      },
      {
       "attempt": 2,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 371.9
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_two_view",
     "arm": "D",
     "strategy": "two_view",
     "seed": 1,
     "admitted": true,
     "admitted_attempt": 0,
     "contract": null,
     "n_raw": 1,
     "n_neutral_valid": 1,
     "n_contract_valid": 1,
     "n_mechanism_pass": 1,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": true,
       "mechanism_pass": true,
       "truncated": false,
       "neutral_detail": "neutral-valid (88 chars)",
       "mechanism_detail": {
        "verdict": "PASS",
        "scenario": "vote2"
       },
       "secs": 200.1
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_decompose",
     "arm": "D",
     "strategy": "decompose",
     "seed": 1,
     "admitted": false,
     "admitted_attempt": null,
     "contract": null,
     "n_raw": 3,
     "n_neutral_valid": 0,
     "n_contract_valid": 0,
     "n_mechanism_pass": 0,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "neutral_detail": "SyntaxError: unterminated string literal (detected at line 164) (p2_D_glm_s1_decompose.py, line 164)",
       "secs": 461.1
      },
      {
       "attempt": 1,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "neutral_detail": "SyntaxError: unterminated string literal (detected at line 130) (p2_D_glm_s1_decompose.py, line 130)",
       "secs": 291.6
      },
      {
       "attempt": 2,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 289.7
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_error_classify",
     "arm": "D",
     "strategy": "error_classify",
     "seed": 1,
     "admitted": false,
     "admitted_attempt": null,
     "contract": null,
     "n_raw": 3,
     "n_neutral_valid": 0,
     "n_contract_valid": 0,
     "n_mechanism_pass": 0,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 303.5
      },
      {
       "attempt": 1,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 514.7
      },
      {
       "attempt": 2,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 285.9
      }
     ]
    },
    {
     "harness": "p2_D_glm_s1_format_guard",
     "arm": "D",
     "strategy": "format_guard",
     "seed": 1,
     "admitted": false,
     "admitted_attempt": null,
     "contract": null,
     "n_raw": 3,
     "n_neutral_valid": 0,
     "n_contract_valid": 0,
     "n_mechanism_pass": 0,
     "attempts": [
      {
       "attempt": 0,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 369.5
      },
      {
       "attempt": 1,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 329.5
      },
      {
       "attempt": 2,
       "neutral_valid": false,
       "mechanism_pass": false,
       "truncated": false,
       "reason": "no python fence",
       "secs": 312.7
      }
     ]
    }
   ],
   "_src": "external dir"
  }
 }
}