// The API stores money as integer minor units (paise). Convert only for display.
const currencyFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
});

export function formatMoney(minorUnits) {
  return currencyFormatter.format((minorUnits ?? 0) / 100);
}

export function formatDateTime(isoString) {
  if (!isoString) return '—';
  return new Date(isoString).toLocaleString('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export function formatDate(isoString) {
  if (!isoString) return '—';
  return new Date(isoString).toLocaleDateString('en-IN', { dateStyle: 'medium' });
}

export const ROLE_LABELS = { admin: 'Administrator', warden: 'Warden', staff: 'Staff', student: 'Student' };

export function initials(name = '') {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('');
}

/** "1,234.50" (rupees, as typed) -> 123450 (paise). Returns NaN for invalid input. */
export function toMinor(rupees) {
  const text = String(rupees ?? '').replace(/,/g, '').trim();
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return NaN;
  return Math.round(parseFloat(text) * 100);
}

/** 123450 (paise) -> "1234.50" for pre-filling an input. */
export function fromMinor(minor) {
  return ((minor ?? 0) / 100).toFixed(2);
}

export const todayISO = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};

/** plural(1, 'payment') -> "1 payment"; plural(3, 'fee') -> "3 fees" */
export const plural = (n, word) => `${n ?? 0} ${word}${n === 1 ? '' : 's'}`;
