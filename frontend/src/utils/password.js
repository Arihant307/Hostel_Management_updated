// Mirrors backend/app/utils/validators.py password_problems() for instant feedback.
// The server remains the authority and re-validates every password.
export const PASSWORD_RULES = [
  { label: 'At least 10 characters', test: (p) => p.length >= 10 },
  { label: 'An uppercase letter', test: (p) => /[A-Z]/.test(p) },
  { label: 'A lowercase letter', test: (p) => /[a-z]/.test(p) },
  { label: 'A number', test: (p) => /[0-9]/.test(p) },
];

export function isStrongPassword(password) {
  return password.length <= 128 && PASSWORD_RULES.every((r) => r.test(password));
}
