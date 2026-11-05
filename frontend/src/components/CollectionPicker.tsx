import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useState } from "react";
import { api } from "../lib/api";
import { rowVariants } from "../lib/motion";
import { useCollections } from "../lib/queries";
import { haptic } from "../lib/telegram";
import { toast } from "../lib/toast";
import type { Collection, Favorite } from "../lib/types";
import { Arch, Photo } from "./archive";
import { IconCheck } from "./icons";
import { Button, cx, inputClass, Sheet } from "./ui";

/**
 * Move a saved find into a collection. When the find is not saved yet it is saved first,
 * so «В коллекцию» works from the item screen too.
 */
export function CollectionPicker({ open, onClose, favoriteId, productId, searchId, current }: {
  open: boolean; onClose: () => void; favoriteId: number | null; productId: number; searchId?: string | null; current: number | null;
}) {
  const qc = useQueryClient();
  const cols = useCollections();
  const [title, setTitle] = useState("");
  const done = () => {
    for (const k of ["favorites", "collections", "item", "results", "me"]) qc.invalidateQueries({ queryKey: [k] });
  };
  const move = useMutation({
    mutationFn: async (cid: number | null) => {
      let fid = favoriteId;
      if (fid === null) fid = (await api.post<Favorite>("/api/v1/favorites", { product_id: productId, search_id: searchId ?? null })).id;
      await api.put(`/api/v1/favorites/${fid}/collection`, { collection_id: cid });
      return cid;
    },
    onSuccess: (cid) => {
      haptic.success();
      const name = cols.data?.find((c) => c.id === cid)?.title;
      toast(cid === null ? "Убрано из коллекции" : `В коллекции «${name ?? "новая"}»`, "good");
      done();
      onClose();
    },
    onError: (e) => { haptic.error(); toast((e as Error).message, "bad"); },
  });
  const create = useMutation({
    mutationFn: (t: string) => api.post<Collection>("/api/v1/collections", { title: t }),
    onSuccess: (c) => { setTitle(""); qc.setQueryData<Collection[]>(["collections"], (xs) => [...(xs ?? []), c]); move.mutate(c.id); },
    onError: (e) => toast((e as Error).message, "bad"),
  });
  return (
    <Sheet open={open} onClose={onClose} title="В коллекцию">
      <ul className="border-t border-line">
        {[{ id: null as number | null, title: "Без коллекции", count: -1, cover_url: null as string | null }, ...(cols.data ?? [])].map((c, i) => (
          <motion.li key={c.id ?? "none"} custom={i} variants={rowVariants} initial="hidden" animate="show">
            <button disabled={move.isPending} onClick={() => move.mutate(c.id)}
              className="flex min-h-[60px] w-full items-center gap-3.5 border-b border-line text-left active:bg-surface-2">
              <Arch className="h-[44px] w-[34px] shrink-0" dashed={!c.id}>
                {c.cover_url ? <Photo src={c.cover_url} alt="" /> : <div className="h-full w-full bg-surface-2" />}
              </Arch>
              <span className="flex-1 text-[15px]">{c.title}</span>
              {c.count >= 0 && <span className="caption text-ink-3">{c.count}</span>}
              <span className={cx("grid h-6 w-6 place-items-center rounded-full", current === c.id ? "bg-ink text-bg" : "")}>
                {current === c.id && <IconCheck size={13} strokeWidth={3} />}
              </span>
            </button>
          </motion.li>
        ))}
      </ul>
      <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (title.trim()) create.mutate(title.trim()); }}>
        <input className={inputClass} maxLength={64} placeholder="Новая коллекция" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Button type="submit" className="h-12 shrink-0" loading={create.isPending} disabled={!title.trim()}>Создать</Button>
      </form>
    </Sheet>
  );
}
