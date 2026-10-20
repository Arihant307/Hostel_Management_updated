export default function Card({ className = '', children, ...props }) {
  return (
    <div
      className={`rounded-xl border border-slate-200 bg-surface shadow-card ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
