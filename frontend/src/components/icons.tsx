/* Minimal 1.5px-stroke icon set (24px grid). */
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };
const base = (size = 22): SVGProps<SVGSVGElement> => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.6,
  strokeLinecap: "round", strokeLinejoin: "round",
});

export const IconSearch = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></svg>);
export const IconHeart = ({ size, filled, ...p }: P & { filled?: boolean }) => (
  <svg {...base(size)} {...p} fill={filled ? "currentColor" : "none"}><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z" /></svg>);
export const IconClock = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><circle cx="12" cy="12" r="8" /><path d="M12 8v4l2.5 2.5" /></svg>);
export const IconUser = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><circle cx="12" cy="8.5" r="3.5" /><path d="M5 20c1.2-3.5 4-5 7-5s5.8 1.5 7 5" /></svg>);
export const IconCamera = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2l1.5-2h6l1.5 2h2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5Z" /><circle cx="12" cy="13" r="3.5" /></svg>);
export const IconImage = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><rect x="4" y="4" width="16" height="16" rx="2" /><circle cx="9" cy="9.5" r="1.5" /><path d="m20 15-4.5-4.5L6 20" /></svg>);
export const IconClipboard = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><rect x="6" y="5" width="12" height="15" rx="2" /><path d="M9 5V4h6v1" /></svg>);
export const IconArrow = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M5 12h14M13 6l6 6-6 6" /></svg>);
export const IconChevron = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="m9 6 6 6-6 6" /></svg>);
export const IconClose = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M6 6l12 12M18 6 6 18" /></svg>);
export const IconFilter = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></svg>);
export const IconGrid = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /></svg>);
export const IconList = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><rect x="4" y="5" width="5" height="5" rx="1" /><rect x="4" y="14" width="5" height="5" rx="1" /><path d="M12 7.5h8M12 16.5h8" /></svg>);
export const IconLock = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><rect x="5.5" y="10.5" width="13" height="9" rx="2" /><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" /></svg>);
export const IconCheck = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>);
export const IconExternal = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M14 5h5v5M19 5l-8 8M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10" /></svg>);
export const IconBell = ({ size, filled, ...p }: P & { filled?: boolean }) => (<svg {...base(size)} {...p} fill={filled ? "currentColor" : "none"}><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15Z" /><path d="M10 20a2 2 0 0 0 4 0" /></svg>);
export const IconTrash = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12" /></svg>);
export const IconRefresh = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M19 12a7 7 0 1 1-2.1-5M19 4v4h-4" /></svg>);
export const IconStar = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="m12 4 2.4 5 5.4.6-4 3.7 1.1 5.4L12 16l-4.9 2.7 1.1-5.4-4-3.7 5.4-.6Z" /></svg>);
export const IconGift = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><rect x="4" y="9" width="16" height="11" rx="1.5" /><path d="M4 13h16M12 9v11M12 9c-1.5-3-5-3.5-5-1.2C7 9 9.5 9 12 9Zm0 0c1.5-3 5-3.5 5-1.2C17 9 14.5 9 12 9Z" /></svg>);
export const IconSettings = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><circle cx="12" cy="12" r="3" /><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8" /></svg>);
export const IconChat = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M5 18.5V7a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H8.5Z" /></svg>);
export const IconShield = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M12 3.5 5 6v5.5c0 4.3 2.9 7.6 7 9 4.1-1.4 7-4.7 7-9V6Z" /></svg>);
export const IconSpark = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.5 2.5M15.2 15.2l2.5 2.5M6.3 17.7l2.5-2.5M15.2 8.8l2.5-2.5" /></svg>);
export const IconCopy = ({ size, ...p }: P) => (<svg {...base(size)} {...p}><rect x="8" y="8" width="11" height="11" rx="2" /><path d="M5 15V6a1 1 0 0 1 1-1h9" /></svg>);
