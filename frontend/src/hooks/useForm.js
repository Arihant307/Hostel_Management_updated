import { useCallback, useState } from 'react';
import { getErrorMessage, getFieldErrors } from '../services/api.js';

/**
 * Minimal form state: values, per-field errors, a general error and submit
 * handling that maps the API's 409/422 field errors back onto inputs.
 */
export default function useForm(initialValues) {
  const [values, setValues] = useState(initialValues);
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const bind = useCallback(
    (field, { type } = {}) => ({
      name: field,
      value: type === 'checkbox' ? undefined : values[field] ?? '',
      checked: type === 'checkbox' ? Boolean(values[field]) : undefined,
      onChange: (e) => {
        const value = type === 'checkbox' ? e.target.checked : e.target.value;
        setValues((v) => ({ ...v, [field]: value }));
        setErrors((er) => (er[field] ? { ...er, [field]: undefined } : er));
      },
      error: errors[field],
    }),
    [values, errors],
  );

  const reset = useCallback((next = initialValues) => {
    setValues(next);
    setErrors({});
    setFormError('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Run `action`; returns its result, or undefined if it failed. */
  const submit = useCallback(async (action, { validate } = {}) => {
    const clientErrors = validate ? validate(values) : {};
    const filtered = Object.fromEntries(Object.entries(clientErrors).filter(([, v]) => v));
    setErrors(filtered);
    setFormError('');
    if (Object.keys(filtered).length) return undefined;
    setSubmitting(true);
    try {
      return await action(values);
    } catch (err) {
      const fields = getFieldErrors(err);
      setErrors(fields);
      if (!Object.keys(fields).length || err?.response?.status === 409) setFormError(getErrorMessage(err));
      return undefined;
    } finally {
      setSubmitting(false);
    }
  }, [values]);

  return { values, setValues, errors, setErrors, formError, setFormError, submitting, bind, reset, submit };
}
