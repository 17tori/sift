import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { IconClock, IconTrash } from "../components/icons";
import { Badge, Button, Empty, ErrorView, PageHeader, Skeleton, Spinner } from "../components/ui";
import { api, qs } from "../lib/api";
import { MODE_LABEL, relative } from "../lib/format";
import { confirm } from "../lib/telegram";
import type { HistoryItem } from "../lib/types";

const STATUS: Record<string, { label: string; tone: "neutral" | "good" | "bad" | "accent" }> = {
  completed: { label: "Готово", tone: "good" }, failed: { label: "Ошибка", tone: "bad" },
  running: { label: "Идёт", tone: "accent" }, queued: { label: "В очереди", tone: "accent" },
};

export default function History() {
  const qc = useQueryClient();
  const q = useInfiniteQuery({
    queryKey: ["history", "all"], initialPageParam: "",
    queryFn: ({ pageParam }) => api.get<{ items: HistoryItem[]; next_cursor: string | null; limited_days: number | null }>(`/api/v1/history${qs({ cursor: pageParam, limit: 20 })}`),
    getNextPageParam: (l) => l.next_cursor ?? undefined,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  const limited = q.data?.pages[0]?.limited_days;

  const remove = async (id: string) => {
    if (!(await confirm("Удалить поиск из истории?"))) return;
    await api.del(`/api/v1/searches/${id}`);
    qc.invalidateQueries({ queryKey: ["history"] });
  };

  return (
    <div className="mx-auto max-w-xl pb-6">
      <PageHeader numeral="VII" label="Журнал" title="Журнал *поступлений*" subtitle={limited ? `Free хранит историю ${limited} дней` : undefined} />
      <div className="px-4">
        {q.isLoading ? (
          <div className="space-y-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-20 rounded-2xl" />)}</div>
        ) : q.isError ? (
          <ErrorView error={q.error} retry={() => q.refetch()} />
        ) : !items.length ? (
          <Empty icon={<IconClock size={26} />} title="Журнал *пуст*" text="Здесь будут все ваши поиски по фото." action={<Link to="/"><Button>Начать поиск</Button></Link>} />
        ) : (
          <ul className="divide-y divide-line overflow-hidden rounded-[20px] bg-surface ring-1 ring-line">
            {items.map((h) => (
              <li key={h.id} className="flex items-center gap-3 p-3">
                <Link to={`/search/${h.id}`} className="flex min-w-0 flex-1 items-center gap-3">
                  <div className="h-16 w-14 shrink-0 overflow-hidden rounded-xl bg-surface-2">
                    {h.image_url && <img src={h.image_url} alt="" className="h-full w-full object-cover" loading="lazy" />}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-[15px] font-medium">{h.title ?? "Фото"}</p>
                    <p className="mt-0.5 text-xs text-ink-3">{relative(h.created_at)} · {MODE_LABEL[h.mode]?.title} · {h.results_count} шт.</p>
                    <div className="mt-1.5"><Badge tone={STATUS[h.status]?.tone}>{STATUS[h.status]?.label ?? h.status}</Badge></div>
                  </div>
                </Link>
                <button onClick={() => remove(h.id)} className="grid h-9 w-9 place-items-center rounded-full text-ink-3" aria-label="Удалить"><IconTrash size={18} /></button>
              </li>
            ))}
          </ul>
        )}
        {q.hasNextPage && (
          <Button variant="secondary" className="mt-4 w-full" onClick={() => q.fetchNextPage()} disabled={q.isFetchingNextPage}>
            {q.isFetchingNextPage ? <Spinner /> : "Показать ещё"}
          </Button>
        )}
      </div>
    </div>
  );
}
