import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { useConfig } from "../lib/queries";
import { haptic, openTelegram } from "../lib/telegram";

const FAQ = [
  { q: "Как считается процент сходства?", a: "Его рассчитывает модель визуальных эмбеддингов, сравнивая ваше фото с фотографиями объявлений. Если модель недоступна, процент не показывается." },
  { q: "Почему некоторые площадки не подключены?", a: "Мы используем только официальные API и партнёрские фиды. У части площадок нет легального способа поиска по чужим объявлениям, поэтому они помечены статусом и не возвращают результатов." },
  { q: "Спишется ли что-то после пробного периода?", a: "Нет. После trial вы вернётесь на Free. Платная подписка оформляется только вручную." },
  { q: "Как отменить подписку?", a: "Раздел «Подписка» → «Автопродление». Доступ сохранится до конца оплаченного периода." },
];

export default function Support() {
  const { data: cfg } = useConfig();
  const [text, setText] = useState("");
  const send = useMutation({
    mutationFn: () => api.post("/api/v1/support", { message: text }),
    onSuccess: () => { haptic.success(); setText(""); },
  });
  return (
    <div className="mx-auto max-w-xl pb-6">
      <PageHeader title="Поддержка" subtitle="Ответим в чате с ботом" />
      <div className="space-y-4 px-4">
        <Card className="p-4">
          <textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} rows={5}
            placeholder="Опишите вопрос или проблему. Если речь о поиске, укажите, что искали."
            className="w-full resize-none rounded-2xl bg-surface-2 p-4 text-[15px] outline-none placeholder:text-ink-3 focus:ring-2 focus:ring-accent/60" />
          {send.isSuccess && <p className="mt-2 text-sm text-good">Сообщение отправлено. Мы ответим в Telegram.</p>}
          {send.error && <p className="mt-2 text-sm text-bad">{(send.error as Error).message}</p>}
          <Button className="mt-3 w-full" disabled={text.trim().length < 3} loading={send.isPending} onClick={() => send.mutate()}>Отправить</Button>
          {cfg?.brand.support_username && (
            <Button variant="ghost" className="mt-1 w-full" onClick={() => openTelegram(`https://t.me/${cfg.brand.support_username}`)}>
              Написать @{cfg.brand.support_username}
            </Button>
          )}
        </Card>
        <div className="space-y-2">
          {FAQ.map((f) => (
            <details key={f.q} className="group rounded-2xl bg-surface p-4 ring-1 ring-line">
              <summary className="cursor-pointer list-none text-[15px] font-medium">{f.q}</summary>
              <p className="mt-2 text-sm leading-relaxed text-ink-2">{f.a}</p>
            </details>
          ))}
        </div>
      </div>
    </div>
  );
}
