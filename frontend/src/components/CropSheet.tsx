import { useCallback, useState } from "react";
import Cropper, { type Area } from "react-easy-crop";
import { Button, Sheet } from "./ui";

async function cropToBlob(src: string, area: Area): Promise<Blob> {
  const img = new Image();
  img.src = src;
  await img.decode();
  const canvas = document.createElement("canvas");
  const scale = Math.min(1, 1600 / Math.max(area.width, area.height));
  canvas.width = Math.round(area.width * scale);
  canvas.height = Math.round(area.height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas unavailable");
  ctx.drawImage(img, area.x, area.y, area.width, area.height, 0, 0, canvas.width, canvas.height);
  return await new Promise((res, rej) => canvas.toBlob((b) => (b ? res(b) : rej(new Error("crop failed"))), "image/jpeg", 0.92));
}

export function CropSheet({ src, open, onClose, onDone }: { src: string | null; open: boolean; onClose: () => void; onDone: (b: Blob) => void }) {
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [area, setArea] = useState<Area | null>(null);
  const [busy, setBusy] = useState(false);
  const onComplete = useCallback((_: Area, px: Area) => setArea(px), []);
  return (
    <Sheet open={open} onClose={onClose} title="Выделите вещь">
      {src && (
        <>
          <div className="relative mt-1 h-[52vh] overflow-hidden rounded-3xl bg-black">
            <Cropper image={src} crop={crop} zoom={zoom} aspect={4 / 5} onCropChange={setCrop} onZoomChange={setZoom}
              onCropComplete={onComplete} objectFit="contain" showGrid={false} />
          </div>
          <input type="range" min={1} max={3} step={0.01} value={zoom} onChange={(e) => setZoom(Number(e.target.value))}
            className="mt-5 w-full accent-[var(--accent)]" aria-label="Масштаб" />
          <p className="mt-2 text-center text-xs text-ink-3">Чем точнее рамка вокруг вещи, тем точнее поиск</p>
          <div className="mt-5 grid grid-cols-2 gap-3">
            <Button variant="secondary" onClick={onClose}>Отмена</Button>
            <Button loading={busy} onClick={async () => {
              if (!area || !src) return;
              setBusy(true);
              try { onDone(await cropToBlob(src, area)); } finally { setBusy(false); }
            }}>Готово</Button>
          </div>
        </>
      )}
    </Sheet>
  );
}
