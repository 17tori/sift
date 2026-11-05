import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { Link, useParams } from "react-router-dom";
import { Arch, Ornament, Photo, Stamp } from "../components/archive";
import { IconExternal } from "../components/icons";
import { Button, ErrorView, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { money } from "../lib/format";
import { ease, wordmarkReveal } from "../lib/motion";
import { cmp } from "../lib/price";
import { openExternal } from "../lib/telegram";
import type { SharedFind as SF } from "../lib/types";

/** Opened from a shared postcard (startapp=f_<token>). */
export default function SharedFind() {
  const { token = "" } = useParams();
  const q = useQuery({ queryKey: ["share", token], queryFn: () => api.get<SF>(`/api/v1/shares/${encodeURIComponent(token)}`) });
  if (q.isError) return <ErrorView error={q.error} retry={() => q.refetch()} />;
  const s = q.data;
  const price = s ? cmp(s.product) : null;
  return (
    <div className="mx-auto max-w-xl px-5 pt-2 pb-10">
      <p className="caption text-center text-ink-3">Находка из архива SIFT</p>
      <motion.h1 className="mt-3 text-center font-serif text-[34px] leading-[36px] font-light" {...wordmarkReveal}>
        {s ? <>{s.sharer_name} <i className="font-normal">делится</i></> : " "}
      </motion.h1>
      <div className="mt-6 flex justify-center">
        <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease: ease.ritual }}>
          <Arch morph className="h-[360px] w-[272px]">
            {s ? <Photo src={s.product.image_url} fallback={s.product.image_fallback_url} alt={s.product.title} /> : <Skeleton className="h-full w-full" />}
          </Arch>
        </motion.div>
      </div>
      {s && (
        <motion.div className="mt-6 text-center" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35, duration: 0.42, ease: ease.outExpo }}>
          <Stamp land>{s.product.marketplace_name}</Stamp>
          <p className="mt-3 text-[16px] leading-[22px]">{s.product.title}</p>
          <p className="mt-2 font-mono text-[24px] font-semibold tnum">{price ? money(price.value, price.currency) : "Цена на сайте"}</p>
          <Ornament className="mx-auto mt-6 w-40 text-relic" draw />
          <Button className="mt-6 w-full" onClick={() => openExternal(s.product.url)}>Открыть на {s.product.marketplace_name} <IconExternal size={17} /></Button>
          {s.search_id ? (
            <Link to={`/search/${s.search_id}`}><Button variant="secondary" className="mt-3 w-full">Открыть мой поиск</Button></Link>
          ) : (
            <Link to="/"><Button variant="secondary" className="mt-3 w-full">Найти свою вещь по фото</Button></Link>
          )}
          <p className="mt-4 text-[12px] leading-[17px] text-ink-3">Цену и наличие проверяйте на сайте площадки.</p>
        </motion.div>
      )}
    </div>
  );
}
