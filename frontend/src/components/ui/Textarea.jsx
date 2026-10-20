import { forwardRef, useId } from 'react';
import { Field } from './Input.jsx';

const Textarea = forwardRef(function Textarea(
  { label, error, hint, required, rows = 4, className = '', id: idProp, ...props },
  ref,
) {
  const autoId = useId();
  const id = idProp || autoId;
  return (
    <Field id={id} label={label} error={error} hint={hint} required={required}>
      <textarea
        ref={ref}
        id={id}
        rows={rows}
        required={required}
        aria-invalid={error ? 'true' : undefined}
        className={`block w-full rounded-lg border bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 ${
          error
            ? 'border-rose-300 focus:border-rose-400 focus:ring-rose-100'
            : 'border-slate-200 focus:border-navy-400 focus:ring-navy-100'
        } ${className}`}
        {...props}
      />
    </Field>
  );
});

export default Textarea;
