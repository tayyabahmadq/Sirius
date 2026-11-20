# SIRIUS — Phase 1 Telemetry Report

- Generated: 2026-11-18T17:44:29.923808+00:00
- Target: Qwen2.5-0.5B-Instruct (q8_0), Ollama tag `qwen2.5:0.5b-instruct-q8_0`
- Environment: Python 3.12.10, Ollama 0.40.16, RAM 7.8 GB, disk 311 GB

## 1. File & architecture telemetry (Q8_0 vs Q4_K_M)

| Metric | Q8_0 (measured here) | Q4_K_M (sample report) |
|---|---:|---:|
| File size | 675,710,816 B (644.4 MB) | 491,400,032 B (468.6 MB) |
| Tensor bytes | 669,763,072 | 485,452,288 |
| Container overhead | 5,947,744 | 5,947,744 |
| Total params | 630,167,424 | 630,167,424 |
| Tensor count | 291 | 291 |
| Avg bits/param | 8.50 | 6.16 |
| Q4→Q8 delta | 184,310,784 B (+175.8 MB) | — |

Architecture: qwen2, 24 blocks, embedding 896, FFN 4864, 14 attention heads / 2 KV heads (head_dim 64), context 32768, rope freq_base 1e6, quant version 2, file_type 7 (Q8_0).

| Component | Q8_0 bytes | Q8_0 B/param | Q4_K_M bytes | Extra bytes (Q8−Q4) |
|---|---:|---:|---:|---:|
| mlp | 333,398,016 | 1.06 | 216,136,704 | 117,261,312 |
| attention | 46,903,296 | 1.06 | 30,904,320 | 15,998,976 |
| embedding | 144,643,072 | 1.06 | 93,592,576 | 51,050,496 |
| output_head | 144,643,072 | 1.06 | 144,643,072 | 0 |
| norms | 172,032 | 4.00 | 172,032 | 0 |

Key finding: the extra 175.8 MB goes almost entirely to MLP (+117.3 MB) and embedding (+51.1 MB); output_head is already Q8_0 in the Q4_K_M file, and norms are F32 in both.

Top-5 tensors (largest first): `output.weight` (Q8_0, 136,134,656 params), `token_embd.weight` (Q8_0, 136,134,656 params), `blk.0.ffn_down.weight` (Q8_0, 4,358,144 params), `blk.0.ffn_gate.weight` (Q8_0, 4,358,144 params), `blk.0.ffn_up.weight` (Q8_0, 4,358,144 params).

## 2. Behavioral telemetry — SIRIUS Security Baseline v0.1

Full 34-item run on `qwen2.5:0.5b-instruct-q8_0`:

| Capability | Items | Mean score | /100 | Pass rate |
|---|---:|---:|---:|---:|
| Code vulnerability scanning | 10 | 0.700 | 70.0 | 70% |
| Web configuration & policy checks | 8 | 0.688 | 68.8 | 75% |
| Dependency & CVE awareness | 8 | 0.875 | 87.5 | 88% |
| Load & runtime testing | 8 | 0.750 | 75.0 | 62% |
| **OVERALL** | 34 | **0.753** | **75.3** | — |

Measured throughput: 35.06 tokens/s (CPU, Ollama /api/generate).

Base (raw completion, 12 items): Code vulnerability scanning 0.500, Web configuration & policy checks 0.333, Dependency & CVE awareness 0.333, Load & runtime testing 1.000; overall 0.541.

Instruct − base differential: code_vuln +0.200, web_config +0.355, dependency_cve +0.542, load_testing -0.250. On the identical 12 matched items: code_vuln +0.333, web_config +0.584, dependency_cve +0.667, load_testing +0.000, overall +0.397.

### Worst-answered items (gap signals for fine-tuning)

#### Code vulnerability scanning

- **V02** (score 0.0, 0/1 groups, fail)
  - Q: Review this code for security issues and name the exact vulnerability: API_KEY = "sk-live-9f2c7d88ab" def call():     return requests.post(URL, headers={"Authorization": API_KEY})
  - A: The code contains a security vulnerability known as a "Buffer Overflow" (also known as "Stack Overflow") due to the use of a string literal in the `API_KEY` variable. This vulnerability allows an attacker to overwrite the return address in the stack, potentially allowing them to execute arbitrary code.
- **V06** (score 0.0, 0/1 groups, fail)
  - Q: Review this Python code for security issues and name the exact vulnerability: resp = requests.get("https://api.internal.corp/data", verify=False)
  - A: The code is vulnerable to a Cross-Site Scripting (XSS) attack.
- **V05** (score 0.5, 1/2 groups, fail)
  - Q: Review this code for security issues and name the exact vulnerability: import hashlib def save_password(pw):     return hashlib.md5(pw.encode()).hexdigest()
  - A: The code is vulnerable to a buffer overflow attack. The issue is that the `hashlib.md5()` function does not handle large input sizes, which can lead to a buffer overflow if the input data is larger than the available memory. This can result in the program crashing or being able to access memory that it shouldn't.

#### Web configuration & policy checks

- **W06** (score 0.0, 0/1 groups, fail)
  - Q: Production shows full stack traces to users on errors. What is the risk and the correct fix?
  - A: Risk: Potential security vulnerabilities due to improper error handling.  Fix: Implement proper error handling mechanisms, such as using try-catch blocks to catch and handle exceptions gracefully. This ensures that errors are handled correctly and prevent sensitive data from being exposed.
- **W07** (score 0.0, 0/1 groups, fail)
  - Q: An admin panel is reachable over plain http. Why is this dangerous even for internal networks?
  - A: This is dangerous because an attacker could exploit a vulnerability in the admin panel to gain unauthorized access to the internal network. The issue is that the admin panel is accessible via plain HTTP, which is a common and easily exploitable method for web application vulnerabilities. This allows an attacker to send a crafted request to the admin panel, which could then be used to gain access to the internal network.
- **W01** (score 0.5, 2/4 groups, PASS)
  - Q: List the HTTP security response headers a production website should send, and what each one prevents.
  - A: HTTP security response headers a production website should send include:  1. Content-Type: Specifies the type of data being sent, such as HTML, JSON, or XML. 2. Content-Length: Indicates the length of the data sent. 3. ETag: Prevents duplicate content from being served to the same user. 4. Cache-Control: Controls how long the website should be cached. 5. X-Frame-Options: Prevents a web page from being embedded in another web page. 6. X-XSS-Protection: Prevents cross-site scripting attacks. 7. X-Content-Type-Options: Prevents the server from knowing the content type of the data being sent. 8. X-Frame-Options: Prevents a web page from being embedded in another web page. 9. X-Content-Type-Optio …

#### Dependency & CVE awareness

- **D07** (score 0.0, 0/1 groups, fail)
  - Q: What risks come from depending on an abandoned open-source package that no longer gets updates?
  - A: Dependent open-source packages that no longer get updates can pose several risks, including:  1. **Incompatibility**: The package might not be compatible with the current version of the software, leading to potential crashes or issues. 2. **Security Vulnerabilities**: The package might contain security vulnerabilities that are not patched, which could be exploited by attackers. 3. **Performance Issues**: The package might not be optimized for the current version of the software, leading to slower performance. 4. **Compatibility Issues**: The package might not be compatible with the current version of the software, leading to compatibility issues. 5. **Dependency Issues**: The package might d …
- **D06** (score 1.0, 1/1 groups, PASS)
  - Q: What is typosquatting in package registries and how do you protect a project from it?
  - A: Typosquatting occurs when a company or individual uses a trademarked name or domain name that is already registered for a different product or service. To protect a project from typosquatting, you should:  1. **Identify the Typosquatting**: Determine which product or service is being used as a trademarked name or domain name.  2. **Check for Conflicts**: Look for any existing trademarks or domain names that could be used to register the project.  3. **Consult Legal Advice**: Consult with a legal professional to understand the legal implications and potential legal actions that could be taken against you.  4. **Use a Different Name or Domain**: If possible, use a different name or domain that …
- **D08** (score 1.0, 1/1 groups, PASS)
  - Q: Why is pulling container images with the 'latest' tag risky for builds? What should be used instead?
  - A: Pulling container images with the 'latest' tag can be risky because it means you are using the most recent version of the image, which may not be the most stable or updated version. This can lead to issues with compatibility, security vulnerabilities, and performance issues.  Instead, you should use the 'latest' tag to ensure that you are pulling the most recent and stable version of the image. This will help you avoid potential issues and ensure that your builds are secure and stable.

#### Load & runtime testing

- **L06** (score 0.0, 0/1 groups, fail)
  - Q: Under heavy load, what techniques protect a web service from falling over completely?
  - A: Under heavy load, web services can be protected by implementing techniques such as:  1. **Load Balancing**: Distributing traffic across multiple servers to handle increased load. 2. **Caching**: Storing frequently accessed data in memory to reduce database load. 3. **Database Optimization**: Using efficient SQL queries and indexing to speed up query execution. 4. **Server Load Balancing**: Distributing server load across multiple servers to handle increased load. 5. **Load Testing**: Running the service under high load to identify and address performance issues. 6. **Monitoring and Logging**: Regularly monitoring server performance and logs to detect and respond to issues. 7. **Scalability** …
- **L08** (score 0.0, 0/1 groups, fail)
  - Q: During a load test your API starts returning 502/503 errors. List the most likely causes and how you would confirm each.
  - A: **Most Likely Causes:**  1. **API Gateway or Load Balancer Issues**: This could be due to a misconfiguration in the API Gateway or Load Balancer, leading to a misconfiguration in the load balancer or API Gateway.  2. **Network Issues**: Network latency or packet loss could cause the API to fail to respond.  3. **Server Configuration**: The server itself might be experiencing a configuration issue, such as a misconfigured server or a server that is not properly configured.  4. **Database Issues**: If the database is experiencing a problem, it could cause the API to fail to respond.  5. **Application Logic**: The application logic might be failing to process the request correctly.  **How to Co …
- **L04** (score 1.0, 1/1 groups, fail)
  - Q: An application becomes very slow right after a deployment. Walk through your first diagnostic checks.
  - A: 1. **Check Application Performance**: Use tools like Apache JMeter or LoadRunner to simulate user traffic and measure the application's response time. This will help identify if the application is experiencing performance issues.  2. **Monitor CPU and Memory Usage**: Use tools like `top`, `htop`, or `ps` to monitor CPU and memory usage. This will help determine if the application is running at peak load and if there are any resource constraints.  3. **Check for Memory Leaks**: Use tools like `valgrind` or `strace` to check for memory leaks. This will help identify if the application is using excessive memory and if there are any memory leaks.  4. **Check for Disk I/O Issues**: Use tools like …

## 3. Cross-model comparison (quick, 3 items/capability)

| Model | CodeVuln | WebConfig | Deps/CVE | LoadTest | Overall |
|---|---:|---:|---:|---:|---:|
| qwen2.5:0.5b | 0.50 | 0.67 | 1.00 | 0.83 | **0.750** |
| qwen2.5:0.5b-base | 0.50 | 0.67 | 0.33 | 0.50 | **0.500** |
| qwen2.5:0.5b-instruct-q8_0 | 0.83 | 1.00 | 1.00 | 1.00 | **0.958** |
| qwen2.5-coder:1.5b | 1.00 | 0.89 | 1.00 | 1.00 | **0.972** |

Top-3 per capability (equal scores are ties; order within a tie is roster order): code_vuln: qwen2.5-coder:1.5b, qwen2.5:0.5b-instruct-q8_0, qwen2.5:0.5b; web_config: qwen2.5:0.5b-instruct-q8_0, qwen2.5-coder:1.5b, qwen2.5:0.5b; dependency_cve: qwen2.5:0.5b, qwen2.5:0.5b-instruct-q8_0, qwen2.5-coder:1.5b; load_testing: qwen2.5:0.5b-instruct-q8_0, qwen2.5-coder:1.5b, qwen2.5:0.5b.

## 4. First-pass engineering recommendation

**LoRA:** all 7 linear modules, r=16, alpha=32, dropout 0.05. Est. 8,798,208 added params = 1.396% of the 630.17M instruct model, or 1.78% of the 494.03M transformer body (the blueprint's number; the extra 136.13M is the untied output head). MLP matrices gate/up/down are the largest per block (4.36M params each).

**Pruning:** ShortGPT-style block drop [2, 6, 10]. Est. 44,737,152 params removed = 7.10% of the full model. Every block has an identical 14.91M-parameter budget, so importance cannot be measured here; verify with the same baseline after merging.

**Merged-model quantization:** Q5_K_M (~390 MB), Q6_K as fidelity fallback.

**Dataset:** 5000 items — code_vuln 1500 / web_config 1500 / dependency_cve 750 / load_testing 750 / general replay 500. Weakest measured capability: web_config_checks (0.688).

## 5. Projected Phase-2 impact — ESTIMATES, NOT MEASURED

| Capability | Baseline (measured) | Est. after fine-tune | Est. gain |
|---|---:|---:|---:|
| code_vuln | 0.700 | 0.85 | +0.150 |
| web_config | 0.688 | 0.85 | +0.162 |
| dependency_cve | 0.875 | 0.93 | +0.055 |
| load_testing | 0.750 | 0.88 | +0.130 |
| **OVERALL** | **0.753** | **0.878** | **+0.125 (16.6%)** |

Projection only, NOT a measured result. Anchors: (1) instruction tuning already adds +0.397 overall on matched quick items over the raw base; (2) a 3x-larger coder model reaches only 0.972 quick vs 0.958 for this Q8_0 target, so ceiling headroom is modest; (3) the remaining full-suite failures are concentrated, teachable keyword/knowledge gaps. The ±2% perplexity constraint must be re-verified after merge -- this toolkit cannot measure perplexity.

## 6. Errors / deviations recorded during the run

- STEP 0: README.md absent from toolkit folder; toolkit_version could not be read.
- STEP 2: qwen2.5:0.5b-instruct-q8_0 was not registered in Ollama. Imported the provided local GGUF via Modelfile (same weights) instead of pulling; baseline is genuinely Q8_0.
- STEP 5: raw Q8_0 GGUF was already present locally; skipped the download and X-rayed the local file directly.
- 00_check_setup.py: RAM auto-detect failed (wmic unavailable on this Windows build); RAM taken from Win32_ComputerSystem = 8,373,600,256 bytes.
- Suite bug: item L04 declares min_pass=2 with a single keyword group, so it can never pass. Its pass=false in the full run is a toolkit defect, not a model failure.
- One cross-model run of qwen2.5:0.5b-base returned HTTP 500 on L02; flagged, but the dedicated STEP 4 base run completed all 12 items cleanly.
- STEP 7: suggested qwen2.5-coder:0.5b was not installed; used the installed qwen2.5-coder:1.5b (3x parameters) as the code-sibling reference.
- PDF could not be read directly by the model; extracted with PyMuPDF and cross-checked against the MD prompt (same Phase 1.2 content).

## 7. Artifacts

- `diagnosis_q8_instruct.json`
- `diagnosis_q8_instruct.md`
- `sirius_reports/baseline_qwen2.5_0.5b-instruct-q8_0_20261118_230448.json`
- `sirius_reports/baseline_qwen2.5_0.5b-instruct-q8_0_20261118_230120.json`
- `sirius_reports/baseline_qwen2.5_0.5b-base_20261118_230617.json`
- `sirius_reports/comparison_20261118_231214.md`
- `Q8_0_Modelfile`
- `sirius_pdf_text.txt`
