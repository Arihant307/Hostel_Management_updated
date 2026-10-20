import { forwardRef, useId, useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

const fieldClass = (error) =>
  `block w-full rounded-lg border bg-white px-3 text-sm text-slate-900 placeholder:text-slate-400 transition-colors focus:outline-none focus:ring-2 disabled:bg-slate-50 disabled:text-slate-500 ${
    error
      ? 'border-rose-300 focus:border-rose-400 focus:ring-rose-100'
      : 'border-slate-200 focus:border-navy-400 focus:ring-navy-100'
  }`;

export function Field({ id, label, error, hint, required, children }) {
  return (
    <div>
      {label && (
        <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-slate-700">
          {label}
          {required && <span className="ml-0.5 text-rose-500">*</span>}
        </label>
      )}
      {children}
      {error ? (
        <p id={`${id}-error`} className="mt-1.5 text-xs text-rose-600">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-1.5 text-xs text-slate-500">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

const Input = forwardRef(function Input(
  { label, error, hint, required, type = 'text', className = '', id: idProp, ...props },
  ref,
) {
  const autoId = useId();
  const id = idProp || autoId;
  const [reveal, setReveal] = useState(false);
  const isPassword = type === 'password';

  return (
    <Field id={id} label={label} error={error} hint={hint} required={required}>
      <div className="relative">
        <input
          ref={ref}
          id={id}
          type={isPassword && reveal ? 'text' : type}
          required={required}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
          className={`h-10 ${isPassword ? 'pr-10' : ''} ${fieldClass(error)} ${className}`}
          {...props}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setReveal((r) => !r)}
            className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-slate-400 hover:text-slate-600"
            aria-label={reveal ? 'Hide password' : 'Show password'}
          >
            {reveal ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
      </div>
    </Field>
  );
});

export const Select = forwardRef(function Select(
  { label, error, hint, required, className = '', id: idProp, children, ...props },
  ref,
) {
  const autoId = useId();
  const id = idProp || autoId;
  return (
    <Field id={id} label={label} error={error} hint={hint} required={required}>
      <select
        ref={ref}
        id={id}
        required={required}
        aria-invalid={error ? 'true' : undefined}
        className={`h-10 pr-8 ${fieldClass(error)} ${className}`}
        {...props}
      >
        {children}
      </select>
    </Field>
  );
});

export default Input;
