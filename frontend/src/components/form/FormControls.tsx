import { ReactNode, useId, useMemo, useState } from 'react';

export function FormSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="form-section">
      <div className="form-section-header">
        <h4>{title}</h4>
        {description && <p>{description}</p>}
      </div>
      <div className="form-section-body">{children}</div>
    </section>
  );
}

export function FormField({
  label,
  hint,
  required,
  error,
  children,
  htmlFor,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  error?: string;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className={`form-field${error ? ' has-error' : ''}`}>
      <label htmlFor={htmlFor}>
        {label}
        {required && <span className="required-mark">*</span>}
      </label>
      {hint && !error && <span className="field-hint">{hint}</span>}
      {children}
      {error && <span className="field-error" role="alert">{error}</span>}
    </div>
  );
}

export function FormRow({ children }: { children: ReactNode }) {
  return <div className="form-row">{children}</div>;
}

export function SelectInput({
  id,
  value,
  onChange,
  options,
  placeholder,
}: {
  id?: string;
  value: string;
  onChange: (v: string) => void;
  options: readonly { value: string; label: string }[] | readonly string[];
  placeholder?: string;
}) {
  const normalized = options.map((o) =>
    typeof o === 'string' ? { value: o, label: o } : o,
  );
  return (
    <select id={id} className="form-control" value={value} onChange={(e) => onChange(e.target.value)}>
      {placeholder && (
        <option value="" disabled>
          {placeholder}
        </option>
      )}
      {normalized.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function CountryCombobox({
  id,
  value,
  onChange,
  countries,
  placeholder = 'Search country…',
}: {
  id?: string;
  value: string;
  onChange: (code: string) => void;
  countries: readonly { code: string; name: string }[];
  placeholder?: string;
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const selected = countries.find((c) => c.code === value);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return countries.filter((c) => c.code !== 'OTHER');
    return countries.filter(
      (c) => c.name.toLowerCase().includes(q) || c.code.toLowerCase().includes(q),
    );
  }, [countries, query]);

  return (
    <div className={`combobox${open ? ' open' : ''}`}>
      <input
        id={id}
        className="form-control"
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        placeholder={selected ? selected.name : placeholder}
        value={open ? query : selected?.name ?? ''}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
      />
      {open && filtered.length > 0 && (
        <ul className="combobox-list" role="listbox">
          {filtered.slice(0, 12).map((c) => (
            <li key={c.code}>
              <button
                type="button"
                role="option"
                aria-selected={c.code === value}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onChange(c.code);
                  setQuery('');
                  setOpen(false);
                }}
              >
                {c.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ChipGroup({
  options,
  selected,
  onToggle,
  multi = true,
}: {
  options: readonly { value: string; label: string }[] | readonly string[];
  selected: string | string[];
  onToggle: (value: string) => void;
  multi?: boolean;
}) {
  const normalized = options.map((o) =>
    typeof o === 'string' ? { value: o, label: o } : o,
  );
  const isSelected = (v: string) =>
    multi ? (selected as string[]).includes(v) : selected === v;

  return (
    <div className="chip-group" role={multi ? 'group' : 'radiogroup'}>
      {normalized.map((o) => (
        <button
          key={o.value}
          type="button"
          className={`chip${isSelected(o.value) ? ' selected' : ''}`}
          aria-pressed={multi ? isSelected(o.value) : undefined}
          aria-checked={!multi ? isSelected(o.value) : undefined}
          role={multi ? 'button' : 'radio'}
          onClick={() => onToggle(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function FileDropZone({
  accept,
  label,
  hint,
  onFile,
}: {
  accept: string;
  label: string;
  hint?: string;
  onFile: (file: File) => void;
}) {
  return (
    <label className="file-drop">
      <input
        type="file"
        accept={accept}
        className="file-drop-input"
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
      />
      <span className="file-drop-icon">↑</span>
      <span className="file-drop-label">{label}</span>
      {hint && <span className="file-drop-hint">{hint}</span>}
    </label>
  );
}

export function ReviewBlock({
  title,
  items,
}: {
  title: string;
  items: { label: string; value: string }[];
}) {
  return (
    <div className="review-block">
      <h5>{title}</h5>
      <dl>
        {items.map(({ label, value }) => (
          <div key={label} className="review-item">
            <dt>{label}</dt>
            <dd>{value || '—'}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function Stepper({
  steps,
  current,
  onStepClick,
}: {
  steps: readonly { id: number; label: string }[];
  current: number;
  onStepClick?: (step: number) => void;
}) {
  return (
    <nav className="stepper" aria-label="Form progress">
      <ol>
        {steps.map((s) => {
          const state = s.id < current ? 'complete' : s.id === current ? 'active' : 'upcoming';
          return (
            <li key={s.id} className={`stepper-item stepper-${state}`}>
              <button
                type="button"
                disabled={!onStepClick || s.id > current}
                onClick={() => onStepClick?.(s.id)}
              >
                <span className="stepper-num">{s.id + 1}</span>
                <span className="stepper-label">{s.label}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** Horizontal connected-dot stepper for multi-page forms. */
export function HorizontalStepper({
  steps,
  current,
}: {
  steps: readonly { id: number; label: string }[];
  current: number;
}) {
  return (
    <nav className="stepper-horizontal" aria-label="Form progress">
      <ol>
        {steps.map((s) => {
          const state = s.id < current ? 'complete' : s.id === current ? 'active' : 'upcoming';
          return (
            <li key={s.id} className={`stepper-h-item stepper-h-${state}`}>
              <span className="stepper-h-dot" aria-hidden />
              <span className="stepper-h-label">{s.label}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function useFieldId(prefix: string) {
  const uid = useId();
  return `${prefix}-${uid}`.replace(/:/g, '');
}
