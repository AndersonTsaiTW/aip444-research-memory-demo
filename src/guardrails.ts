// Write-time guardrails: the "code enforces" half of "model proposes, code enforces".
// Even if the model tries to save something malicious, these deny-rules block it before
// it reaches storage. This maps onto the Write phase of the memory lifecycle
// (Lin et al., 2026) and Dash et al. (2026)'s poisoning defenses.

export type GuardrailRule =
  | "behavior-override" // poisoning: instructions that change the agent's rules
  | "secret-credential" // passwords, API keys, card numbers
  | "third-party-pii"; // sensitive personal data about someone else

export interface GuardrailResult {
  blocked: boolean;
  rule?: GuardrailRule;
  reason?: string;
}

// Rule 1: behaviour-override / memory-poisoning signatures
const BEHAVIOR_OVERRIDE_PATTERNS: RegExp[] = [
  /\bignore\b.*\b(warning|warnings|instruction|instructions|rule|rules|safety|guardrail)/i,
  /\b(all future|from now on|always)\b.*\b(warning|warnings|safety|security|check|checks)\b.*\b(are|is)\b.*\b(false|fake|ignored|disabled)/i,
  /\b(disable|bypass|turn off|override)\b.*\b(safety|security|guardrail|filter|check)/i,
  /\b(you must|you should) (always|never)\b.*\b(ignore|bypass|reveal|disable)/i,
  /\bsecurity warnings?\b.*\b(are|is)\b.*\b(false|fake)/i,
  /\btreat\b.*\b(instruction|command)s?\b.*\bas (trusted|safe|verified)/i,
];

//Rule 2: secrets / credentials
const SECRET_PATTERNS: RegExp[] = [
  /\b(password|passwd|pwd|passphrase)\b\s*(is|=|:)/i,
  /\bapi[\s_-]?key\b/i,
  /\bsecret[\s_-]?(key|token)\b/i,
  /\bsk-[A-Za-z0-9]{6,}/, // OpenAI/OpenRouter-style keys
];

// Rule 3: third-party sensitive personal data 
// Heuristic: a health/sensitive condition attributed to a named other person.
const THIRD_PARTY_SUBJECT = /\b(my |his |her |their )?(roommate|friend|coworker|colleague|neighbor|neighbour|boss|sister|brother|mother|father|mom|dad|cousin|ex|partner)\b/i;
const SENSITIVE_CONDITION = /\b(depression|hiv|std|cancer|pregnan|bipolar|schizophreni|addict|rehab|abortion|diagnos|mental (health|illness)|suicid|therapy|medication|salary|arrest|criminal record)\b/i;
const NAMED_PERSON_CONDITION = /\b[A-Z][a-z]+\b.*\b(has|is|was|suffers|struggles)\b.*(depression|hiv|std|cancer|pregnan|bipolar|schizophreni|addict|diagnos|suicid)/;

/**
 * Inspect the content a tool wants to write. If any deny-rule matches, return blocked=true
 * with the rule and a human-readable reason. Otherwise blocked=false.
 *
 * We check the memory content AND (optionally) the originating user message, because a poisoning
 * instruction can arrive phrased as an innocuous-looking "fact".
 */
export function checkWrite(content: string, sourceMessage = ""): GuardrailResult {
  const haystack = `${content}\n${sourceMessage}`;

  for (const re of BEHAVIOR_OVERRIDE_PATTERNS) {
    if (re.test(haystack)) {
      return {
        blocked: true,
        rule: "behavior-override",
        reason: "attempt to store an instruction that changes agent behavior/safety rules (poisoning signature)",
      };
    }
  }

  for (const re of SECRET_PATTERNS) {
    if (re.test(haystack)) {
      return {
        blocked: true,
        rule: "secret-credential",
        reason: "attempt to store a secret or credential",
      };
    }
  }

  if (
    NAMED_PERSON_CONDITION.test(haystack) ||
    (THIRD_PARTY_SUBJECT.test(haystack) && SENSITIVE_CONDITION.test(haystack))
  ) {
    return {
      blocked: true,
      rule: "third-party-pii",
      reason: "attempt to store sensitive personal data about a third party",
    };
  }

  return { blocked: false };
}
