import { Check, Circle } from 'lucide-react';
import Input from './ui/Input.jsx';
import { PASSWORD_RULES } from '../utils/password.js';

export function PasswordChecklist({ value }) {
  return (
    <ul className="grid gap-1.5 sm:grid-cols-2" aria-label="Password requirements">
      {PASSWORD_RULES.map((rule) => {
        const ok = rule.test(value || '');
        return (
          <li key={rule.label} className={`flex items-center gap-2 text-xs ${ok ? 'text-emerald-700' : 'text-slate-500'}`}>
            {ok ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : <Circle className="h-3.5 w-3.5 text-slate-300" aria-hidden="true" />}
            {rule.label}
            <span className="sr-only">{ok ? '(met)' : '(not met)'}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** New password + confirmation with a live requirements checklist. */
export default function PasswordFields({ form, field = 'password', confirm = 'confirm_password', label = 'Password' }) {
  return (
    <div className="space-y-3">
      <Input label={label} type="password" required autoComplete="new-password" {...form.bind(field)} />
      <PasswordChecklist value={form.values[field]} />
      <Input label={`Confirm ${label.toLowerCase()}`} type="password" required autoComplete="new-password" {...form.bind(confirm)} />
    </div>
  );
}

export function validatePasswordPair(values, isStrong, field = 'password', confirm = 'confirm_password') {
  return {
    [field]: !isStrong(values[field] || '') && 'Password does not meet the requirements.',
    [confirm]: values[confirm] !== values[field] && 'Passwords do not match.',
  };
}
