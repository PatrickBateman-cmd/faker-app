import type { Toast } from "../../hooks/useToast";

interface Props {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}

export function ToastContainer({ toasts, onDismiss }: Props) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`px-4 py-3 rounded shadow-lg text-sm text-white transition-opacity duration-300 ${
            toast.type === "success"
              ? "bg-green-600"
              : toast.type === "error"
                ? "bg-red-600"
                : "bg-blue-600"
          }`}
          style={{ animation: "fadeIn 0.2s ease-out" }}
        >
          <div className="flex items-center justify-between gap-2">
            <span>{toast.message}</span>
            <button
              onClick={() => onDismiss(toast.id)}
              className="text-white/70 hover:text-white leading-none"
            >
              &times;
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
