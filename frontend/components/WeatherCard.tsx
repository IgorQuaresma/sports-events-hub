import type { Weather } from "@/lib/api";
import { formatDate } from "@/lib/format";
import Icon from "./Icon";

const fmt = (n: number | null, unit: string) => (n == null ? "–" : `${Math.round(n)}${unit}`);

/** Race-day forecast; renders nothing unless a forecast exists (race within ~16 days). */
export default function WeatherCard({ weather }: { weather: Weather | null }) {
  if (!weather?.available || !weather.date) return null;
  return (
    <section className="card space-y-3" aria-labelledby="weather-title">
      <h2 id="weather-title" className="flex items-center gap-2 text-base font-semibold">
        <Icon name="sun" className="h-5 w-5 text-accent-500" /> Race-day forecast
      </h2>
      <p className="text-sm text-slate-600">{formatDate(weather.date, { weekday: "long", day: "numeric", month: "long" })}</p>
      <p className="text-lg font-semibold text-slate-900">{weather.summary ?? "Forecast"}</p>
      <dl className="grid grid-cols-3 gap-2 text-center text-sm">
        <div className="rounded-lg bg-slate-50 p-2">
          <dt className="text-xs text-slate-500">Temp.</dt>
          <dd className="font-semibold">{fmt(weather.temp_min_c, "°")} / {fmt(weather.temp_max_c, "°C")}</dd>
        </div>
        <div className="rounded-lg bg-slate-50 p-2">
          <dt className="text-xs text-slate-500">Rain</dt>
          <dd className="font-semibold">{fmt(weather.precipitation_probability_pct, " %")}</dd>
        </div>
        <div className="rounded-lg bg-slate-50 p-2">
          <dt className="text-xs text-slate-500">Wind</dt>
          <dd className="font-semibold">{fmt(weather.wind_max_kmh, " km/h")}</dd>
        </div>
      </dl>
      <p className="text-xs text-slate-500">
        <a href={weather.attribution_url} target="_blank" rel="noopener noreferrer" className="underline">{weather.attribution}</a>
        {" "}· forecasts change, check again before the race.
      </p>
    </section>
  );
}
