import { Card, Field, PageHeader, Segmented } from "../components/ui";
import { MODE_LABEL } from "../lib/format";
import { useMe, usePreferences } from "../lib/queries";
import { useUi } from "../lib/store";
import type { Mode, Preferences } from "../lib/types";

const CURRENCIES = ["RUB", "USD", "EUR", "CNY", "GBP", "KZT"];

export default function Settings() {
  const { data: me } = useMe();
  const prefs = usePreferences();
  const { view, setView } = useUi();
  const p = me?.preferences ?? {};
  const save = (x: Preferences) => prefs.mutate(x);
  return (
    <div className="mx-auto max-w-xl pb-6">
      <PageHeader title="Настройки" />
      <div className="space-y-4 px-4">
        <Card className="space-y-5 p-4">
          <Field label="Тема">
            <Segmented value={p.theme ?? "system"} onChange={(theme) => save({ theme })}
              options={[{ value: "system", label: "Как в Telegram" }, { value: "light", label: "Светлая" }, { value: "dark", label: "Тёмная" }]} />
          </Field>
          <Field label="Вид результатов">
            <Segmented value={view} onChange={(v) => { setView(v); save({ view: v }); }} options={[{ value: "grid", label: "Сетка" }, { value: "list", label: "Список" }]} />
          </Field>
          <Field label="Режим поиска по умолчанию">
            <Segmented value={p.default_mode ?? "similar"} onChange={(m: Mode) => save({ default_mode: m })}
              options={(["exact", "similar", "cheaper", "discover"] as Mode[]).map((m) => ({ value: m, label: MODE_LABEL[m].title, locked: !me?.plan.features.modes?.includes(m) }))} />
          </Field>
          <Field label="Валюта для сравнения цен">
            <div className="flex flex-wrap gap-2">
              {CURRENCIES.map((c) => (
                <button key={c} onClick={() => save({ currency: c })}
                  className={`h-9 rounded-full px-3.5 font-mono text-[13px] ${(p.currency ?? (me?.language_code?.startsWith("ru") ? "RUB" : "USD")) === c ? "bg-ink text-bg" : "bg-surface-2 text-ink-2"}`}>{c}</button>
              ))}
            </div>
            <p className="mt-2 text-xs text-ink-3">Цены показываются в валюте площадки; пересчёт ≈ по курсу ЦБ РФ.</p>
          </Field>
        </Card>
      </div>
    </div>
  );
}
