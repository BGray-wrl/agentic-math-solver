
  Files of record                                             

  - experiments/results/openproblems_full_report.md — comprehensive table                                
  - experiments/results/openproblems_consensus_v2_*.json × 4 — all consensus runs
  - experiments/results/openproblems_gemma_phase1_*_*.json — gemma phase 1                               
  - experiments/results/openproblems_gemma_seedfull_*_*.json × 2 — seed_full + roleswap                  
  - experiments/_kakeya_verifier.py — full forcing-pair semantics check                                  
  - experiments/_lr_verifier.py — Littlewood-Richardson coefficient verifier                             
  - experiments/_gemini_api.py — adaptive Gemini API client                                              
  - logs/openproblems_*.jsonl — raw candidate text for every trial                                       
                                                                                             

  Negative results (judges fooled)

  - inverse-galois: 13 unanimous "correct" labels across all conditions. All 30+ submissions
  fail the disc-square check (M_n ⊆ A_n requires perfect-square discriminant; none have one).
  - arithmetic-kakeya: 1 unanimous correct (roleswap). Forcing pair traces show 8/9 vertices
  unforced — mathematically invalid.
  - stretched-lr-coefficients: 4 unanimous correct. All have either zero LR values or a
  constant polynomial (no negative coefficient).
  - large-steiner-systems: 1 unanimous correct. Block coverage 525/792 (incomplete).
  - ramsey-book-graphs: 2 unanimous correct. Adjacency string lengths wrong.
  - hadamard, klt-del-pezzo, q2-absolute-galois: have judges saying "correct" but no local
  verifier exists; don't trust them.

  Headline conclusion

  Across ~380 trials × 4 conditions × 3 generator architectures, neither gemma-4-31b alone,
  nor seed_full ideation+verify-revise loop, nor cross-model role swap improved over the
  baseline. Zero new locally-verified solutions came from any of the new experiments. The
  added 30 "consensus correct" labels were all wrong on the problems where we could check.

  Spend

  ~$13 of $40 budget total. Gemini API was effectively free; OpenRouter paid for judges +
  oss-xhigh in roleswap.

  Files of record

  - experiments/results/openproblems_full_report.md — comprehensive table
  - experiments/results/openproblems_consensus_v2_*.json × 4 — all consensus runs
  - experiments/results/openproblems_gemma_phase1_*_*.json — gemma phase 1
  - experiments/results/openproblems_gemma_seedfull_*_*.json × 2 — seed_full + roleswap
  - experiments/_kakeya_verifier.py — full forcing-pair semantics check
  - experiments/_lr_verifier.py — Littlewood-Richardson coefficient verifier
  - experiments/_gemini_api.py — adaptive Gemini API client
  - logs/openproblems_*.jsonl — raw candidate text for every trial
---

Here's the complete picture of what came out of the run. The recap missed a meaningful-chunke—s/     
  particularly the Phase 3 "revise top" + Phase 4 "strong passN" attempts, the v1 (mistaken-spec) -solv
  consensus run, several partial/mock pass@5 JSONs, and 14 raw JSONL logs.                             
                                                                                                       
  FrontierMath open-problems — full artifact inventory                                        
                                                                                                       
  A. Scripts (24 files, all experiments/)                                                              
                                                                                                       
  Phase 1 — generation pass@5                                                                          
  - openproblems_pass5_20260507.py — gpt-oss-120b xhigh + deepseek-v4-flash via OpenRouter,            
  deepseek-v4-flash judge.                                                                             
  - openproblems_gemma_phase1_20260507.py — gemma-4-31b-it via direct Gemini API (tier 2), once        
  OpenRouter was found to share a single Google upstream account.                                      
  - openproblems_gemma_passN_20260507.py — smaller gemma-only generate-only fallback after seed_full   
  saturated the 8-concurrency semaphore.                                                               
                                                                                                       
  Phase 2 — consensus judging                                                                          
  - openproblems_consensus_judge_20260507.py — v1: gpt-oss xhigh + gemini-3.1-pro + deepseek (the      
  "wrong" lineup; gemini-3.1-pro is too tightly coupled with the others).                              
  - openproblems_consensus_v2_20260507.py — v2: oss-xhigh + deepseek 2-judge (per your spec).          
                                                                                                       
  Phase 3 — refinement (NOT in the recap)                                                              
  - openproblems_revise_top_20260507.py — verify↔revise loop on Phase 1 positives (push partial →      
  almost → correct).                                                                                   
  - openproblems_seed_full_20260507.py — ideate(N)→branches→V↔R; killed early when 8-conc gemma blocked
   the outer pool.                                                                                     
  - openproblems_gemma_seedfull_20260507.py — replacement at reduced scope (warmup × 1 seed × 2 ideas ×
   1 V↔R), homogeneous + roleswap.
                                                                                                       
  Phase 4 — frontier escalation (NOT in the recap)                                                   
  - openproblems_strong_passN_20260507.py — claude-opus-4.6 / gemini-3.1-pro pass@N on positive-signal 
  problems. Not clear it actually executed; no strong_passN_* JSON exists.                             
   
  Verification                                                                                         
  - openproblems_local_verify_20260507.py (28K, biggest) — local checkers for hadamard, Steiner,     
  Ramsey-book, small-Diophantine, degree-sensitivity-boolean, explicit-deformations, inverse-galois    
  necessary cond.                                                                                  
  - _kakeya_verifier.py — full forcing-pair semantics check.                                           
  - _lr_verifier.py — Littlewood-Richardson stretched coefficient verifier.                          
  - check_galois_polys_20260507.py — standalone disc-square + irreducibility (the inverse-Galois       
  confabulation killer).                                                                               
                                                                                                       
  Reporting / glue (NOT in the recap)                                                                  
  - openproblems_summary_20260507.py — judge-label distribution, per-problem positive rate.            
  - openproblems_final_report_20260507.py — produces results/openproblems_final_report.txt.            
  - openproblems_full_report_20260507.py — produces results/openproblems_full_report.md.               
  - _gemini_api.py — adaptive Gemini client (4–20 conc based on 429 cascades).                         
  - _log_to_phase1_json.py — JSONL→consensus-input converter.                                        
  - _parse_partial_consensus.py — recover the 55-record partial consensus run from console output.     
                                                                                                       
  B. Result JSONs (15 in experiments/results/)                                                         
                                                                                                       
  Phase 1                                                                                              
  - openproblems_pass5_…_181650_mock.json (mock smoke, 4.5K)                                         
  - openproblems_pass5_…_181709.json (early partial, 1.3K, 3 records)                                  
  - openproblems_pass5_…_182455.json (934K — looks complete-ish but only 3 top-level records; trial  
  data is nested)                                                                                      
  - openproblems_gemma_phase1_…_210520.json (11K early)                                                
  - openproblems_gemma_phase1_…_221534.json (813K — complete 120 trials)                               
                                                                                                       
  Seed-full                                                                                            
  - …seedfull_…gemma_homogeneous_…231726.json (518K, 12 trials)                                        
  - …seedfull_…roleswap_oss_verify_…231828.json (781K, 12 trials)                                      
                                                                                                       
  Consensus v1 (the wrong lineup, NOT in the recap)                                                    
  - openproblems_consensus_judge_…_184327.json (81K, 9 records — this is what produced the 3-judge     
  unanimous false-positives on inverse-galois, since gemini-3.1-pro was in the panel).                 
                                                                                                       
  Consensus v2 — five separate files because of multiple kicks                                         
  - …_221732.json (335K, 30) | …_221802.json (263K, 18) | …_231818.json (181 B — empty) | …_231905.json
   (90K, 6) | …_233252.json (104K, 7). Aggregated to 111 entries in the report.                        
                                                                                                       
  Partial consensus rescue (NOT in the recap)                                                          
  - consensus_partial_55.json + consensus_partial_55_log.txt — 55 entries scraped from console after 
  the v1 consensus stalled on gpt-oss judge calls.                                                     
                                                  
  C. Raw logs (14 in logs/, ~32 MB total)                                                              
                                                                                                       
  The recap mentioned "raw candidate text" but didn't enumerate. The headliners:                       
  - openproblems_pass5_…_183859.jsonl (26 MB, 246 trials — this is the canonical Phase 1 record)       
  - openproblems_gemma_phase1_…_210937.jsonl (799K, 120 trials — full gemma)                           
  - …seedfull_…gemma_homogeneous_…222634.jsonl (505K, 12) | …roleswap_…222646.jsonl (768K, 12)       
  - Plus 10 short partial / restart fragments.                                                         
                                                                                                       
  D. Reports (3 in results/, NOT all in the recap)                                                     
                                                                                                       
  - results/openproblems_full_report.md — comprehensive table (this is what was cited).                
  - results/openproblems_final_report.txt — earlier text version: shows 14 verified passes including 6
  "PASS necessary conditions only" arithmetic-kakeya entries (later downgraded once _kakeya_verifier.py
   checked forcing-pair semantics).                                                                  
  - results/openproblems_phase1_report.md — the Phase 1-specific writeup with the inverse-galois       
  confabulation case study and "what would close the verification gap" section. Not mentioned in the   
  recap.
                                                                                                       
  E. Inputs (benchmarks/frontiermath-open-problems/)                                                   
   
  - open_problems_prompts.csv (39K) | open_problems_survey.csv (6.5K)                                  
  - ramsey-hypergraphs/ (excluded per project_openproblems_excluded.md) + extract script + reference 
  solution CSV.                                                                                        
                                                                                                     

  - results/openproblems_full_report.md — comprehensive table (this is what was cited).
  - results/openproblems_final_report.txt — earlier text version: shows 14 verified passes including 6 "PASS necessary conditions
  only" arithmetic-kakeya entries (later downgraded once _kakeya_verifier.py checked forcing-pair semantics).
  - results/openproblems_phase1_report.md — the Phase 1-specific writeup with the inverse-galois confabulation case study and "what
  would close the verification gap" section. Not mentioned in the recap.

  ---
  What this changes about the headline


  The recap's "zero new locally-verified solutions came from any of the new
  experiments" still stands — but the audit trail is more textured than the recap

  1. Phase 3 revise_top and Phase 4 strong_passN were attempted but produced no result
   JSONs under those names. Worth verifying whether they actually ran or were
  abandoned mid-implementation; the recap silently dropped them.
  2. Two consensus runs, not one: the v1 (gemini-3.1-pro panelist) is what generated
  the most spectacular inverse-galois false-positives; v2 (oss + deepseek) is what's
  reported. Both files are on disk and the v1 results are still informing the "30
  unanimous correct, 22 wrong" count via the report aggregator.
  3. The _final_report.txt shows 14 "verified" passes vs the _full_report.md's 8 — the
   gap is the 6 arithmetic-kakeya "necessary conditions only" entries that were
  downgraded once the full forcing-pair verifier landed. That downgrade is itself the
  most important methodological finding.
  4. openproblems_phase1_report.md is a self-contained writeup with the inverse-galois
   case study; if you're sharing the work externally that report is more readable than
   the bare table in _full_report.md.

  Net: the actual deliverables from this run are 24 scripts, 15 result JSONs, 14 logs,
   3 reports — roughly double what the recap enumerated. The scientific conclusion is
  unchanged; the artifact trail is more complete.
