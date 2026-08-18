import type { ReactNode } from 'react';
import { Button } from './Primitives';

interface ModalProps {
  title: string;
  children: ReactNode;
  onClose: () => void;
  actions?: ReactNode;
  variant?: 'default' | 'error';
}

export function Modal({ title, children, onClose, actions, variant = 'default' }: ModalProps) {
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className={`modal-card modal-card--${variant}`}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="modal-title" className="modal-title">{title}</h2>
        <div className="modal-body">{children}</div>
        <div className="modal-actions">
          {actions ?? (
            <Button variant="primary" onClick={onClose}>OK</Button>
          )}
        </div>
      </div>
    </div>
  );
}
