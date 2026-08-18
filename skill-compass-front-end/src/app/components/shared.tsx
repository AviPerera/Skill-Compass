import React from "react";

// Color palette
export const colors = {
  forestGreen: "#14532D",
  deepGreen: "#166534",
  limeGreen: "#84CC16",
  softLime: "#D9F99D",
  lightBg: "#F8FAF5",
  white: "#FFFFFF",
  lightGrey: "#E5E7EB",
  medGrey: "#9CA3AF",
  darkGrey: "#1F2937",
  nearBlack: "#111827",
  emerald: "#10B981",
  teal: "#14B8A6",
  skyBlue: "#0EA5E9",
  amber: "#F59E0B",
  slateGrey: "#64748B",
};

export const chartColors = [
  "#14532D", "#166534", "#10B981", "#84CC16",
  "#14B8A6", "#0EA5E9", "#F59E0B", "#64748B",
];

// KPI Card
interface KPICardProps {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}

export function KPICard({ label, value, sub, accent = colors.forestGreen }: KPICardProps) {
  return (
    <div style={{
      background: "#fff",
      borderRadius: 8,
      padding: "10px 14px",
      borderTop: `3px solid ${accent}`,
      boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
      display: "flex",
      flexDirection: "column",
      justifyContent: "center",
      flex: 1,
      minWidth: 0,
    }}>
      <div style={{ fontSize: 10, color: colors.medGrey, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: colors.nearBlack, lineHeight: 1.1 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: colors.medGrey, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

// Chart container card
interface ChartCardProps {
  title: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}

export function ChartCard({ title, children, style }: ChartCardProps) {
  return (
    <div style={{
      background: "#fff",
      borderRadius: 8,
      boxShadow: "0 1px 4px rgba(0,0,0,0.07)",
      border: `1px solid ${colors.lightGrey}`,
      display: "flex",
      flexDirection: "column",
      overflow: "hidden",
      ...style,
    }}>
      <div style={{
        padding: "8px 12px",
        borderBottom: `1px solid ${colors.lightGrey}`,
        fontSize: 12,
        fontWeight: 600,
        color: colors.darkGrey,
        background: "#FAFAFA",
      }}>{title}</div>
      <div style={{ flex: 1, padding: "8px", overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {children}
      </div>
    </div>
  );
}

// Insight card
interface InsightCardProps {
  bullets: string[];
  title?: string;
}

export function InsightCard({ bullets, title = "Key Insights" }: InsightCardProps) {
  return (
    <div style={{
      background: colors.softLime,
      borderRadius: 8,
      padding: "10px 14px",
      border: `1px solid #BEF264`,
    }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: colors.forestGreen, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {title}
      </div>
      {bullets.map((b, i) => (
        <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 6, marginBottom: 3 }}>
          <div style={{ width: 5, height: 5, borderRadius: "50%", background: colors.forestGreen, marginTop: 4, flexShrink: 0 }} />
          <div style={{ fontSize: 11, color: colors.darkGrey, lineHeight: 1.4 }}>{b}</div>
        </div>
      ))}
    </div>
  );
}

// Slicer chip button
interface SlicerChipProps {
  label: string;
  selected: boolean;
  onClick: () => void;
}

export function SlicerChip({ label, selected, onClick }: SlicerChipProps) {
  return (
    <button
      onClick={onClick}
      type="button"
      aria-pressed={selected}
      style={{
        padding: "4px 10px",
        borderRadius: 4,
        border: `1px solid ${selected ? colors.forestGreen : colors.lightGrey}`,
        background: selected ? colors.forestGreen : "#fff",
        color: selected ? "#fff" : colors.darkGrey,
        fontSize: 11,
        fontWeight: selected ? 600 : 400,
        cursor: "pointer",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </button>
  );
}

// Slicer dropdown
interface SlicerDropdownProps {
  label: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
}

export function SlicerDropdown({ label, options, value, onChange }: SlicerDropdownProps) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ fontSize: 10, color: colors.medGrey, fontWeight: 600, textTransform: "uppercase", whiteSpace: "nowrap" }}>{label}</span>
      <select
        aria-label={label}
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          padding: "3px 8px",
          borderRadius: 4,
          border: `1px solid ${colors.lightGrey}`,
          background: "#fff",
          color: colors.darkGrey,
          fontSize: 11,
          cursor: "pointer",
          outline: "none",
        }}
      >
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

// Navigation button
interface NavButtonProps {
  label: string;
  active: boolean;
  onClick: () => void;
}

export function NavButton({ label, active, onClick }: NavButtonProps) {
  return (
    <button
      onClick={onClick}
      type="button"
      aria-current={active ? "page" : undefined}
      style={{
        padding: "6px 12px",
        borderRadius: 0,
        border: "none",
        borderBottom: active ? `3px solid ${colors.limeGreen}` : "3px solid transparent",
        background: active ? colors.forestGreen : "rgba(255,255,255,0.1)",
        color: active ? "#fff" : "rgba(255,255,255,0.75)",
        fontSize: 11,
        fontWeight: active ? 700 : 400,
        cursor: "pointer",
        whiteSpace: "nowrap",
        transition: "all 0.15s",
      }}
    >
      {label}
    </button>
  );
}

// Report Header
interface ReportHeaderProps {
  pageTitle: string;
  currentPage: number;
  onPageChange: (page: number) => void;
  dataAsOf: string;
  totalJobs: number;
}

const navPages = [
  { label: "Executive Summary", pageIndex: 0 },
  { label: "Skills Analysis", pageIndex: 1 },
  { label: "Role Analysis", pageIndex: 2 },
  { label: "Location Insights", pageIndex: 3 },
  // Temporary: retain the implemented page while its governed outputs are completed.
  { label: "Graduate Roadmap", pageIndex: 4, isVisible: false },
  { label: "Methodology", pageIndex: 5 },
];

export function ReportHeader({ pageTitle, currentPage, onPageChange, dataAsOf, totalJobs }: ReportHeaderProps) {
  return (
    <div style={{ background: colors.forestGreen, flexShrink: 0 }}>
      {/* Top title bar */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "8px 20px",
        borderBottom: "1px solid rgba(255,255,255,0.15)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 4,
            background: colors.limeGreen,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 14, fontWeight: 800, color: colors.forestGreen,
          }}>A</div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#fff", lineHeight: 1.2 }}>
              Skill Compass - Navigating Australia’s Data Analytics Job Market Through Skill Intelligence
            </div>
            <div style={{ fontSize: 10, color: "rgba(255,255,255,0.65)" }}>
              {pageTitle} • Data as of {dataAsOf} • 3,088 Collected → 3,028 Validated → Python Pipeline (Skill Extraction &amp; Classification) → {totalJobs.toLocaleString()} Eligible &amp; Relevant Jobs Analysed
            </div>
          </div>
        </div>
        <div style={{ fontSize: 10, color: "rgba(255,255,255,0.6)" }}>University Capstone Project</div>
      </div>
      {/* Nav buttons */}
      <div style={{ display: "flex", paddingLeft: 8 }}>
        {navPages.filter((page) => page.isVisible !== false).map((page) => (
          <NavButton
            key={page.label}
            label={page.label}
            active={page.pageIndex === currentPage}
            onClick={() => onPageChange(page.pageIndex)}
          />
        ))}
      </div>
    </div>
  );
}

// Slicer bar
interface SlicerBarProps {
  children: React.ReactNode;
}

export function SlicerBar({ children }: SlicerBarProps) {
  return (
    <div style={{
      background: "#fff",
      borderBottom: `1px solid ${colors.lightGrey}`,
      padding: "6px 20px",
      display: "flex",
      alignItems: "center",
      gap: 16,
      flexShrink: 0,
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: colors.forestGreen, textTransform: "uppercase", letterSpacing: "0.05em" }}>Filters:</div>
      {children}
    </div>
  );
}

// Horizontal bar for skills
interface HBarProps {
  data: { name: string; value: number; color?: string }[];
  maxValue?: number;
  unit?: string;
}

export function HBarList({ data, maxValue, unit = "%" }: HBarProps) {
  const max = Math.max(1, maxValue ?? Math.max(0, ...data.map(d => d.value)));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1, justifyContent: "space-evenly" }}>
      {data.map((item, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ fontSize: 10, color: colors.darkGrey, width: 110, textAlign: "right", flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.name}</div>
          <div style={{ flex: 1, background: colors.lightGrey, borderRadius: 2, height: 14, overflow: "hidden" }}>
            <div style={{
              width: `${(item.value / max) * 100}%`,
              height: "100%",
              background: item.color ?? chartColors[i % chartColors.length],
              borderRadius: 2,
              display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 3,
            }}>
              <span style={{ fontSize: 9, color: "#fff", fontWeight: 600 }}>{item.value}{unit}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// Donut chart (pure CSS/SVG)
interface DonutProps {
  data: { name: string; value: number; color: string }[];
  size?: number;
}

export function DonutChart({ data, size = 120 }: DonutProps) {
  const total = data.reduce((s, d) => s + d.value, 0);
  let offset = 0;
  const r = 40;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * r;

  const segments = data.map(d => {
    const pct = total ? d.value / total : 0;
    const seg = { ...d, pct, offset };
    offset += pct;
    return seg;
  });

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, flex: 1, justifyContent: "center" }}>
      <svg width={size} height={size} style={{ flexShrink: 0 }}>
        {segments.map((seg, i) => (
          <circle
            key={i}
            cx={cx} cy={cy} r={r}
            fill="none"
            stroke={seg.color}
            strokeWidth={22}
            strokeDasharray={`${seg.pct * circumference} ${circumference}`}
            strokeDashoffset={-seg.offset * circumference}
            transform={`rotate(-90 ${cx} ${cy})`}
          />
        ))}
        <circle cx={cx} cy={cy} r={28} fill="#fff" />
        <text x={cx} y={cy - 4} textAnchor="middle" fontSize={10} fontWeight="700" fill={colors.nearBlack}>{total.toLocaleString()}</text>
        <text x={cx} y={cy + 10} textAnchor="middle" fontSize={8} fill={colors.medGrey}>total</text>
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {data.map((d, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{ width: 8, height: 8, borderRadius: 2, background: d.color, flexShrink: 0 }} />
            <div style={{ fontSize: 10, color: colors.darkGrey }}>{d.name}</div>
            <div style={{ fontSize: 10, fontWeight: 600, color: colors.nearBlack, marginLeft: 2 }}>{total ? Math.round(d.value / total * 100) : 0}%</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Column chart (pure SVG)
interface ColChartProps {
  data: { name: string; value: number; color?: string }[];
  height?: number;
}

export function ColumnChart({ data, height = 120 }: ColChartProps) {
  const max = Math.max(1, ...data.map(d => d.value));
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
      <div style={{ flex: 1, display: "flex", alignItems: "flex-end", gap: 6, paddingBottom: 0 }}>
        {data.map((d, i) => (
          <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: 1 }}>
            <div style={{ fontSize: 9, fontWeight: 600, color: colors.darkGrey, marginBottom: 2 }}>{d.value}</div>
            <div style={{
              width: "100%",
              height: `${(d.value / max) * height}px`,
              background: d.color ?? chartColors[i % chartColors.length],
              borderRadius: "3px 3px 0 0",
              minHeight: 4,
            }} />
          </div>
        ))}
      </div>
      <div style={{ display: "flex", borderTop: `1px solid ${colors.lightGrey}` }}>
        {data.map((d, i) => (
          <div key={i} style={{ flex: 1, textAlign: "center", fontSize: 9, color: colors.medGrey, paddingTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.name}</div>
        ))}
      </div>
    </div>
  );
}

// Simple table
interface SimpleTableProps {
  columns: string[];
  rows: string[][];
  accentCol?: number;
}

export function SimpleTable({ columns, rows, accentCol }: SimpleTableProps) {
  return (
    <div style={{ overflow: "auto", flex: 1 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
        <thead>
          <tr style={{ background: colors.forestGreen }}>
            {columns.map((col, i) => (
              <th key={i} style={{ padding: "5px 8px", textAlign: "left", color: "#fff", fontWeight: 600, whiteSpace: "nowrap" }}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} style={{ background: ri % 2 === 0 ? "#fff" : "#F9FAF8" }}>
              {row.map((cell, ci) => (
                <td key={ci} style={{
                  padding: "4px 8px",
                  color: ci === accentCol ? colors.forestGreen : colors.darkGrey,
                  fontWeight: ci === accentCol ? 600 : 400,
                  borderBottom: `1px solid ${colors.lightGrey}`,
                  whiteSpace: "nowrap",
                }}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Matrix heatmap
interface MatrixProps {
  rows: string[];
  cols: string[];
  data: number[][];
}

export function MatrixHeatmap({ rows, cols, data }: MatrixProps) {
  const max = Math.max(1, ...data.flat());
  const getColor = (v: number) => {
    const pct = v / max;
    if (pct > 0.75) return colors.forestGreen;
    if (pct > 0.5) return "#166534";
    if (pct > 0.25) return colors.limeGreen;
    return colors.softLime;
  };
  const getTextColor = (v: number) => {
    const pct = v / max;
    return pct > 0.25 ? "#fff" : colors.darkGrey;
  };

  return (
    <div style={{ overflow: "auto", flex: 1 }}>
      <table style={{ borderCollapse: "collapse", fontSize: 9, width: "100%" }}>
        <thead>
          <tr>
            <th style={{ padding: "3px 6px", textAlign: "left", color: colors.medGrey }}></th>
            {cols.map(col => (
              <th key={col} style={{ padding: "3px 6px", color: colors.darkGrey, fontWeight: 600, textAlign: "center" }}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              <td style={{ padding: "3px 6px", fontWeight: 600, color: colors.darkGrey, whiteSpace: "nowrap" }}>{row}</td>
              {data[ri].map((val, ci) => (
                <td key={ci} style={{
                  padding: "4px 6px",
                  textAlign: "center",
                  background: getColor(val),
                  color: getTextColor(val),
                  fontWeight: 600,
                  borderRadius: 2,
                  margin: 1,
                }}>{val}%</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
