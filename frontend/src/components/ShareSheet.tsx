import { useMutation } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { postcardIn } from "../lib/motion";
import { copyText, haptic, shareMessage } from "../lib/telegram";
import { toast } from "../lib/toast";
import type { Share } from "../lib/types";
import { IconCopy } from "./icons";
import { Sieve } from "./Sieve";
import { Button, Sheet } from "./ui";

/** Share a find as an archive postcard: the server renders the card, the sheet shows it before sending. */
export function ShareSheet({ open, onClose, productId, searchId }: { open: boolean; onClose: () => void; productId: number; searchId?: string | null }) {
  const [loaded, setLoaded] = useState(false);
  const m = useMutation({
    mutationFn: () => api.post<Share>("/api/v1/shares", { product_id: productId, search_id: searchId ?? null }),
    onError: () => haptic.error(),
  });
  const { mutate, reset } = m;
  useEffect(() => {
    if (open) { setLoaded(false); mutate(); } else reset();
  }, [open, productId, mutate, reset]);
  const s = m.data;
  const send = async () => {
    if (!s) return;
    const sent = await shareMessage(s.prepared_message_id, s.link, s.text);
    if (sent) { haptic.success(); onClose(); }
  };
  return (
    <Sheet open={open} onClose={onClose} title="Открытка находки">
      <div className="flex flex-col items-center">
        <div className="relative aspect-[4/5] w-[min(76vw,300px)]">
          <AnimatePresence>
            {(!s || !loaded) && !m.isError && (
              <motion.div key="wait" className="absolute inset-0 grid place-items-center rounded-[6px] bg-surface-2 text-ink" exit={{ opacity: 0 }}>
                <div className="flex flex-col items-center gap-4">
                  <Sieve cols={11} width={72} animate="breathe" />
                  <span className="caption text-ink-3">Печатаем открытку…</span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          {s && (
            <motion.img src={s.image_url} alt="Открытка с находкой" onLoad={() => { setLoaded(true); haptic.tap(); }}
              className="absolute inset-0 h-full w-full rounded-[6px] object-cover shadow-[0_18px_40px_-12px_rgba(0,0,0,.55)]"
              initial={postcardIn.initial} animate={loaded ? postcardIn.animate : postcardIn.initial} transition={postcardIn.transition} />
          )}
          {m.isError && <p className="absolute inset-0 grid place-items-center px-6 text-center text-sm text-ink-2">{(m.error as Error).message}</p>}
        </div>
        <p className="mt-5 max-w-[300px] text-center text-[13px] leading-[18px] text-ink-2">
          Друг откроет находку по ссылке. Если он впервые в боте, он придёт по вашему приглашению.
        </p>
        <div className="mt-5 grid w-full grid-cols-[1fr_auto] gap-2.5">
          <Button disabled={!s} onClick={send}>Отправить в чат</Button>
          <Button variant="secondary" disabled={!s} aria-label="Скопировать ссылку"
            onClick={async () => { if (s && (await copyText(s.link))) toast("Ссылка скопирована", "good"); }}>
            <IconCopy size={18} />
          </Button>
        </div>
      </div>
    </Sheet>
  );
}
