import { REG_STATE, regStateLabel, timeAgo } from "@/lib/format";
import Icon, { type IconName } from "./Icon";

const TONE: Record<string, string> = {
  green: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  blue: "bg-sky-50 text-sky-800 ring-sky-600/20",
  amber: "bg-amber-50 text-amber-900 ring-amber-600/25",
  red: "bg-rose-50 text-rose-800 ring-rose-600/20",
  gray: "bg-slate-100 text-slate-700 ring-slate-500/20",
};
// Icons make the state readable without relying on colour alone (WCAG 1.4.1).
const ICON: Record<string, IconName> = {
  open: "check", not_open: "clock", waitlist: "clock", sold_out: "x", closed: "x", unknown: "info",
};

export default function RegistrationBadge({
  state, checkedAt, short = false,
}: { state: string; checkedAt?: string | null; short?: boolean }) {
  const meta = REG_STATE[state] ?? REG_STATE.unknown;
  return (
    <span
      className={`badge ring-1 ring-inset ${TONE[meta.tone]}`}
      title={checkedAt ? `Checked ${timeAgo(checkedAt)}` : undefined}
    >
      <Icon name={ICON[state] ?? "info"} className="h-3.5 w-3.5" />
      {short ? meta.short : regStateLabel(state)}
    </span>
  );
}
