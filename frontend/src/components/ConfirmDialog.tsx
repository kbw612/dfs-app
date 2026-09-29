// Shared confirm popover -- replaces window.confirm() (which blocks the
// whole tab and looks like a browser chrome element, not part of the
// app) everywhere an action needs a "this will overwrite something,
// continue?" style confirmation. Reuses the same modal-backdrop/
// modal-dialog/modal-header/modal-close classes MonthCalendar.tsx's date
// picker popover already established, so this doesn't introduce a second
// modal visual language.
//
// message is a ReactNode (not just a string) so a caller with structured
// content -- e.g. WeeklyStatsUpload's per-position Add/Update summary --
// can pass its own JSX (a CSS grid, in that case, so the values line up
// regardless of label width) instead of being limited to one line of
// plain text. Rendered inside a div, not a p, so it's safe for a caller
// to nest block-level content.
import type { ReactNode } from "react";

interface ConfirmDialogProps {
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  message,
  confirmLabel = "Continue",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal-dialog confirm-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span>Confirm</span>
          <button type="button" className="modal-close" onClick={onCancel} aria-label="Close">
            ×
          </button>
        </div>
        <div className="confirm-dialog-message">{message}</div>
        <div className="confirm-dialog-actions">
          <button type="button" className="confirm-dialog-cancel" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button type="button" className="player-pool-save-button" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
