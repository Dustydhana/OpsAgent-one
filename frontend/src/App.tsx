import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Archive,
  BarChart3,
  AudioLines,
  Bell,
  BookOpen,
  Bot,
  Boxes,
  CheckCircle2,
  ChevronsLeft,
  ChevronsRight,
  ChevronRight,
  ChevronDown,
  Cloud,
  CloudCog,
  Cpu,
  Cable,
  Copy,
  Database,
  Download,
  Eye,
  Filter,
  Gauge,
  KeyRound,
  LockKeyhole,
  LogOut,
  Mail,
  Menu,
  MoreHorizontal,
  MessageSquare,
  Mic,
  MonitorCog,
  Paperclip,
  PackageCheck,
  Phone,
  PhoneForwarded,
  Play,
  Plug,
  Search,
  RefreshCw,
  Send,
  Server,
  ServerCog,
  Settings as SettingsIcon,
  ShieldCheck,
  Sparkles,
  SlidersHorizontal,
  Terminal,
  Trash2,
  Users,
  Workflow,
  X,
} from "lucide-react";
import { api, apiErrorMessage, apiUrl } from "./api";
import type { LucideIcon } from "lucide-react";
import { FaAws, FaGithub, FaGoogle, FaMicrosoft, FaSlack, FaWindows } from "react-icons/fa6";
import { GrHpe } from "react-icons/gr";
import {
  SiBroadcom,
  SiAtlassian,
  SiCisco,
  SiDell,
  SiGmail,
  SiGrafana,
  SiLinux,
  SiJira,
  SiVmware,
} from "react-icons/si";
import { TbBrandAzure } from "react-icons/tb";

type Organization = {
  organization_id: string;
  name: string;
  slug: string;
  organization_role: string;
  status: string;
};
type User = {
  username: string;
  display_name: string;
  role: string;
  organization_id?: string;
  organization_role?: string;
  name?: string;
  organizations?: Organization[];
};

const displayRole = (role?: string) => (role === "Owner" ? "Root" : role || "");

type Summary = {
  total: number;
  powered_on: number;
  powered_off: number;
  unknown: number;
  production: number;
  test: number;
  providers: Record<string, number>;
};
type Machine = {
  server_name: string;
  status: string;
  vm_type: string;
  environment: string;
  os_type: string;
  private_ip_address: string;
  ip_address: string;
  application: string;
  application_team: string;
  aws_instance_id: string;
  aws_region?: string;
  public_ip_address?: string;
  os_version?: string;
  server_team?: string;
  monitoring_service?: string;
  important_services?: string[];
  tags?: string[];
  gateway_ip?: string;
  remote_port?: number;
  private_dns_name?: string;
  public_dns_name?: string;
  host_name?: string;
  instance_type?: string;
  architecture?: string;
  availability_zone?: string;
  vpc_id?: string;
  subnet_id?: string;
  storage_volumes?: Array<{
    volume_id?: string;
    device?: string;
    size_gib?: number;
    volume_type?: string;
    iops?: number;
    throughput_mibps?: number;
    encrypted?: boolean;
    state?: string;
    delete_on_termination?: boolean;
  }>;
  notes?: string;
  enabled?: boolean;
};

function machineIconKind(machine: Machine) {
  const os = `${machine.os_type || ""} ${machine.os_version || ""}`.toLowerCase();
  const provider = (machine.vm_type || "").toLowerCase();
  const tags = (machine.tags || []).join(" ").toLowerCase();
  if (os.includes("windows")) return "windows";
  if (os.includes("linux")) return "linux";
  if (/unix|aix|solaris|hp-ux/.test(os)) return "unix";
  if (/cisco|ucs/.test(tags)) return "cisco";
  if (/dell/.test(tags)) return "dell";
  if (/hpe|hewlett|vendor=hp\b/.test(tags)) return "hpe";
  if (provider === "aws") return "aws";
  if (provider === "azure") return "azure";
  if (provider === "vmware") return "vmware";
  if (["physical", "onprem", "on-prem"].includes(provider)) return "physical";
  return "server";
}

function machineIcon(machine: Machine): ReactNode {
  switch (machineIconKind(machine)) {
    case "windows": return <FaWindows />;
    case "linux": return <SiLinux />;
    case "unix": return <Terminal />;
    case "aws": return <FaAws />;
    case "azure": return <TbBrandAzure />;
    case "vmware": return <SiVmware />;
    case "cisco": return <SiCisco />;
    case "dell": return <SiDell />;
    case "hpe": return <GrHpe />;
    default: return <Server />;
  }
}

function connectorIcon(provider: string): ReactNode {
  switch (provider) {
    case "aws": return <FaAws />;
    case "azure": return <TbBrandAzure />;
    case "vmware": return <SiVmware />;
    case "cisco": return <SiCisco />;
    case "dell": return <SiDell />;
    case "hpe": return <GrHpe />;
    case "slack": return <FaSlack />;
    case "gmail": return <SiGmail />;
    case "grafana": return <SiGrafana />;
    case "windows": return <FaWindows />;
    case "linux": return <SiLinux />;
    default: return <Plug />;
  }
}

type InventoryNode = {
  id: string;
  label: string;
  icon: ReactNode;
  children?: InventoryNode[];
};
type Health = {
  Component: string;
  Status: string;
  "Last heartbeat": string;
  Details: string;
};
type Preferences = {
  ui_version?: string;
  theme: string;
  font_size: string;
  density: string;
  timezone: string;
  date_format: string;
  model_provider: string;
  model_name: string;
  email_notifications: boolean;
  operation_notifications: boolean;
  extensions: Record<string, boolean>;
};
type AiConfiguration = {
  mode: "platform" | "byok" | "self_hosted";
  provider: "openai" | "openai_compatible";
  model: string;
  endpoint: string;
  api_key_configured: boolean;
  ready: boolean;
};
type Recognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: (event: {
    results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }>;
  }) => void;
  onend: () => void;
  onerror: () => void;
};

function applyPreferences(p: Preferences) {
  const selected =
    p.theme === "system"
      ? window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark"
      : p.theme;
  const root = document.documentElement;
  root.dataset.theme = selected;
  root.dataset.fontSize = p.font_size;
  root.dataset.density = p.density;
}

function OpsLogo({ small = false }: { small?: boolean }) {
  return (
    <div className={`brand-mark ops-logo ${small ? "small" : ""}`}>
      <img src="/opsagent-mark.svg" alt="OpsAgent One" />
    </div>
  );
}

const BRAND_TAGLINE = "Every operation. Powered by secure intelligence.";

function BrandLockup({ compact = false }: { compact?: boolean }) {
  return <div className={`brand-lockup ${compact ? "compact" : ""}`}><OpsLogo small={compact} /><div><strong>OpsAgent One</strong><span>{BRAND_TAGLINE}</span></div></div>;
}

const navGroups = [
  {
    label: "Workspace",
    items: [
      ["Dashboard", BarChart3],
      ["OpsAgent chat", Bot],
      ["Service desk agent", MessageSquare],
      ["Agent orchestration", Cpu],
    ],
  },
  {
    label: "Integrations",
    items: [["Connections", Cable]],
  },
  {
    label: "Inventory",
    items: [
      ["Server inventory", Server],
      ["Decommission inventory", Archive],
      ["Hardware inventory", ServerCog],
    ],
  },
  {
    label: "Cloud operations",
    items: [
      ["AWS operations", FaAws],
      ["Azure operations", TbBrandAzure],
    ],
  },
  {
    label: "Operating system operations",
    items: [
      ["Windows operations", FaWindows],
      ["Linux operations", SiLinux],
    ],
  },
  {
    label: "Endpoint & patching",
    items: [
      ["SCCM operations", PackageCheck],
    ],
  },
  {
    label: "On-premises operations",
    items: [
      ["VMware operations", SiVmware],
      ["Hardware monitoring", ServerCog],
    ],
  },
  {
    label: "Monitoring operations",
    items: [
      ["Slack alerts", FaSlack],
      ["Gmail alerts", SiGmail],
      ["Agent health", Activity],
      ["Live logs", AudioLines],
    ],
  },
  {
    label: "Governance",
    items: [
      ["AI usage & cost", Sparkles],
      ["Account & access", Users],
      ["Settings", SettingsIcon],
      ["Documentation", BookOpen],
    ],
  },
] as const;

const workspaceRoutes: Record<string, string> = {
  "Dashboard": "dashboard", "OpsAgent chat": "chat", "Service desk agent": "service-desk",
  "Agent orchestration": "agent-orchestration", "Connections": "connections",
  "Server inventory": "inventory/servers", "Decommission inventory": "inventory/decommission",
  "Hardware inventory": "inventory/hardware", "AWS operations": "operations/aws",
  "Azure operations": "operations/azure", "Windows operations": "operations/windows",
  "Linux operations": "operations/linux", "SCCM operations": "operations/sccm",
  "VMware operations": "operations/vmware", "Hardware monitoring": "monitoring/hardware",
  "Slack alerts": "monitoring/slack", "Gmail alerts": "monitoring/gmail",
  "Agent health": "monitoring/agents", "Live logs": "monitoring/logs",
  "AI usage & cost": "governance/ai-usage", "Account & access": "governance/access",
  "Settings": "settings", "Documentation": "documentation",
};
const routePages = Object.fromEntries(Object.entries(workspaceRoutes).map(([page, route]) => [`/app/${route}`, page]));
function pageFromPath(pathname: string) { return routePages[pathname.replace(/\/+$/, "") || "/"]; }
function pathForPage(page: string) { return `/app/${workspaceRoutes[page] || "dashboard"}`; }

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [demoIndex, setDemoIndex] = useState(0);
  const [heroWordIndex, setHeroWordIndex] = useState(0);
  const [capabilityIndex, setCapabilityIndex] = useState(0);
  const [demoOpen, setDemoOpen] = useState(false);
  const [publicDocsOpen, setPublicDocsOpen] = useState(() => location.hash === "#documentation");
  const [authPageOpen, setAuthPageOpen] = useState(() => location.hash === "#signin");
  const [signupMode, setSignupMode] = useState(false);
  const [signupForm, setSignupForm] = useState({ username: "", password: "", country: "India", mobile_number: "" });
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoError, setDemoError] = useState("");
  const [demoResult, setDemoResult] = useState("");
  const [providers, setProviders] = useState<
    { id: string; label: string; configured: boolean }[]
  >([]);
  const [demoForm, setDemoForm] = useState({ full_name: "", business_email: "", company: "", job_role: "", phone: "", estate_size: "", interests: ["AWS", "Windows", "SCCM"], message: "", website: "" });
  const heroWords = ["Discover", "Request", "Acknowledge", "Investigate", "Approve", "Operate", "Verify", "Secure"];
  const capabilities = [
    { title: "Cloud operations", icon: Cloud, kicker: "AWS LIVE · AZURE AND VMWARE FOUNDATION", heading: "Operate cloud resources through provider actions.", description: "OpsAgent discovers cloud inventory and converts requests from the web app, Slack or email into scoped, approval-controlled operations.", bullets: ["AWS inventory and selected EC2/EBS operations are live", "Azure and VMware workspace foundations are present", "GCP and Oracle Cloud are roadmap connectors"], metrics: [["AWS", "Live"], ["Azure", "Foundation"], ["GCP/OCI", "Roadmap"]], rows: ["EC2 lifecycle operation", "EBS volume expansion", "Snapshot request verified"] },
    { title: "Monitoring response", icon: Activity, kicker: "GRAFANA DEMO · CHANNEL WORKFLOWS LIVE", heading: "Acknowledge alerts, investigate context and coordinate response.", description: "Monitoring events can enter through collaboration channels, where OpsAgent acknowledges the incident, gathers infrastructure evidence and proposes a response.", bullets: ["Slack and Gmail request/approval workflows are implemented", "Grafana-to-channel incident demonstration is available", "Datadog, SolarWinds, Nagios and Outlook require production connectors"], metrics: [["Channels", "Slack/Gmail"], ["Grafana", "Demo"], ["More tools", "Roadmap"]], rows: ["Alert acknowledged", "Diagnostics collected", "Approval requested"] },
    { title: "Patch intelligence", icon: CheckCircle2, kicker: "SCCM INVENTORY LIVE · DEPLOYMENT CONTROL NEXT", heading: "Coordinate the complete Windows patch lifecycle.", description: "OpsAgent combines SCCM endpoint data with release intake, test windows, change approval, stakeholder communication, compliance tracking and validation evidence.", bullets: ["Live SCCM inventory through an allowlisted SSM document", "Persistent monthly patch pipeline and approval stages", "SCCM deployment mutation, Intune and Ivanti remain to be enabled"], metrics: [["SCCM", "Live read-only"], ["Pipeline", "Built"], ["Intune/Ivanti", "Roadmap"]], rows: ["KB release intake", "Test collection readiness", "Post-patch validation"] },
    { title: "Server automation", icon: Terminal, kicker: "WINDOWS SSM LIVE · LINUX CATALOG FOUNDATION", heading: "Standardize recurring Windows and Linux administration.", description: "Typed runbooks resolve the exact server, require an approval phrase, execute through a controlled connector and verify the resulting state.", bullets: ["Windows SSM managed-node operations are working", "Windows feature installation is verified end to end", "Linux catalog exists; production execution coverage is still expanding"], metrics: [["Windows", "Live"], ["SSM", "Verified"], ["Linux", "Foundation"]], rows: ["Windows feature installed", "Service operation approved", "Final state verified"] },
    { title: "Governance and audit", icon: ShieldCheck, kicker: "CROSS-CUTTING PRODUCT CONTROL", heading: "Preserve human authority over every infrastructure change.", description: "Tenant RBAC, exact approval, before/after state, command results and operational history provide a consistent control layer across every connector.", bullets: ["Organization-scoped identity and role-based access", "Approval-gated execution with deterministic policy", "Persistent PostgreSQL audit, logs and email notifications"], metrics: [["Access", "RBAC"], ["Changes", "Approved"], ["Evidence", "Persistent"]], rows: ["Requester identified", "Approver recorded", "Execution evidence retained"] },
  ];
  const productMegaGroups = [
    { title:"Operational intelligence", items:[
      {name:"Monitoring Agent",description:"Correlate alerts, investigate impact and coordinate response.",icon:Activity,href:"#demo"},
      {name:"Inventory Intelligence",description:"Unify active and decommissioned assets across every domain.",icon:Database,href:"#platform"},
      {name:"Agent Orchestration",description:"Coordinate specialized agents through one control plane.",icon:Workflow,href:"#capabilities"},
    ]},
    { title:"Infrastructure automation", items:[
      {name:"Cloud Operations",description:"Operate AWS, Azure and hybrid cloud resources safely.",icon:CloudCog,href:"#product-cloud"},
      {name:"Operating Systems",description:"Administer Windows and Linux with approved runbooks.",icon:ServerCog,href:"#product-os"},
      {name:"Endpoint & Patching",description:"Move updates through test, approval and verification.",icon:PackageCheck,href:"#product-patching"},
    ]},
    { title:"Control and connectivity", items:[
      {name:"Enterprise Connections",description:"Connect monitoring, cloud, ITSM and customer gateways.",icon:Cable,href:"#integrations"},
      {name:"Security & Evidence",description:"Apply RBAC, MFA, approvals and persistent audit evidence.",icon:ShieldCheck,href:"#security"},
      {name:"Documentation",description:"Deployment guidance, architecture and integration runbooks.",icon:BookOpen,href:"#documentation"},
    ]},
  ];
  const platformLogos: { brand: string; category: string; name: string; logo: ReactNode }[] = [
    { brand: "aws", category: "Cloud", name: "Amazon Web Services", logo: <FaAws /> },
    { brand: "azure", category: "Cloud", name: "Microsoft Azure", logo: <TbBrandAzure /> },
    { brand: "vmware", category: "Virtualization", name: "VMware by Broadcom", logo: <><SiVmware /><SiBroadcom /></> },
    { brand: "windows", category: "Operating system", name: "Windows Server", logo: <FaWindows /> },
    { brand: "linux", category: "Operating system", name: "Linux", logo: <SiLinux /> },
    { brand: "unix", category: "Operating system", name: "Unix", logo: <Terminal /> },
    { brand: "sccm", category: "Endpoint management", name: "Microsoft SCCM", logo: <FaMicrosoft /> },
    { brand: "intune", category: "Endpoint management", name: "Microsoft Intune", logo: <FaMicrosoft /> },
    { brand: "ivanti", category: "Endpoint management", name: "Ivanti", logo: <span className="word-mark">ivanti</span> },
    { brand: "cisco", category: "Hardware", name: "Cisco UCS", logo: <SiCisco /> },
    { brand: "dell", category: "Hardware", name: "Dell Technologies", logo: <SiDell /> },
    { brand: "hpe", category: "Hardware", name: "HPE", logo: <GrHpe /> },
    { brand: "ibm", category: "Hardware", name: "IBM", logo: <span className="word-mark ibm-mark">IBM</span> },
    { brand: "atlassian", category: "Change management", name: "Atlassian", logo: <SiAtlassian /> },
    { brand: "jira", category: "Change management", name: "Jira", logo: <SiJira /> },
    { brand: "servicenow", category: "IT service management", name: "ServiceNow", logo: <span className="word-mark servicenow-mark">servicenow</span> },
    { brand: "slack", category: "Collaboration", name: "Slack", logo: <FaSlack /> },
    { brand: "gmail", category: "Communication", name: "Gmail", logo: <SiGmail /> },
    { brand: "outlook", category: "Communication", name: "Microsoft Outlook", logo: <Mail /> },
    { brand: "grafana", category: "Observability", name: "Grafana", logo: <SiGrafana /> },
    { brand: "solarwinds", category: "Observability", name: "SolarWinds", logo: <span className="word-mark solarwinds-mark">SolarWinds</span> },
    { brand: "nagios", category: "Observability", name: "Nagios", logo: <span className="word-mark nagios-mark">NAGIOS</span> },
  ];
  const demos = [
    { src: "/opsagent-chat-demo.mp4", label: "Guarded operations from OpsAgent Chat", flow: "Request → acknowledgement → approval → verified completion" },
    { src: "/opsagent-slack-demo.mp4", label: "Coordinated incident response in Slack", flow: "Grafana alert → acknowledgement → diagnostics → notification" },
    { src: "/opsagent-gmail-demo.mp4", label: "Approval-controlled operations from Gmail", flow: "Request → target confirmation → approval → verified result" },
  ];
  const currentDemo = demos[demoIndex];
  const activeCapability = capabilities[capabilityIndex];
  const ActiveCapabilityIcon = activeCapability.icon;
  const authProviders = [{ id: "google", label: "Google", icon: FaGoogle }, { id: "microsoft", label: "Microsoft", icon: FaMicrosoft }, { id: "github", label: "GitHub", icon: FaGithub }];
  useEffect(() => {
    fetch(apiUrl("/auth/providers"))
      .then((r) => r.json())
      .then(setProviders)
      .catch(() => setProviders([]));
  }, []);
  useEffect(() => {
    const timer = window.setInterval(
      () => setHeroWordIndex((current) => (current + 1) % heroWords.length),
      3200,
    );
    return () => window.clearInterval(timer);
  }, []);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch(apiUrl("/auth/login"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(apiErrorMessage(data.detail, "Unable to sign in"));
      localStorage.setItem("opsagent_token", data.access_token);
      onLogin(data.user);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function submitSignup(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const response = await fetch(apiUrl("/auth/signup"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(signupForm) });
      const data = await response.json();
      if (!response.ok) throw new Error(apiErrorMessage(data.detail, "Unable to create account"));
      localStorage.setItem("opsagent_token", data.access_token);
      onLogin(data.user);
    } catch (signupError) {
      setError((signupError as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function submitDemo(e: FormEvent) {
    e.preventDefault();
    setDemoBusy(true);
    setDemoError("");
    try {
      const response = await fetch(apiUrl("/public/demo-requests"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(demoForm) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Unable to submit the request");
      setDemoResult(result.request_id);
    } catch (requestError) {
      setDemoError((requestError as Error).message);
    } finally {
      setDemoBusy(false);
    }
  }
  const openDemo = (event?: React.MouseEvent) => {
    event?.preventDefault();
    setDemoError("");
    setDemoResult("");
    setDemoOpen(true);
  };
  const openPublicDocs = (event?: React.MouseEvent) => {
    event?.preventDefault();
    history.pushState(null, "", "#documentation");
    setPublicDocsOpen(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const closePublicDocs = () => {
    history.pushState(null, "", location.pathname);
    setPublicDocsOpen(false);
    window.scrollTo({ top: 0 });
  };
  const openAuthPage = (event?: React.MouseEvent) => {
    event?.preventDefault();
    setPublicDocsOpen(false);
    setAuthPageOpen(true);
    history.pushState(null, "", "#signin");
    window.scrollTo({ top: 0 });
  };
  const openPublicSection = (hash: string) => {
    setPublicDocsOpen(false);
    history.pushState(null, "", `${location.pathname}${hash}`);
    window.setTimeout(() => document.querySelector(hash)?.scrollIntoView({ behavior: "smooth" }), 0);
  };
  if (authPageOpen) return (
    <main className="public-auth-page">
      <button className="auth-back" onClick={() => { setAuthPageOpen(false); history.pushState(null, "", location.pathname); }}><ChevronRight/> Back to website</button>
      <div className="auth-grid-pattern" aria-hidden="true">
        <svg className="auth-flow-lines" viewBox="0 0 1300 900" preserveAspectRatio="none"><path d="M-60 55 C185 85 90 390 365 450 H1300"/><path d="M-60 190 C155 215 135 405 365 450 H1300"/><path d="M-60 320 C150 325 175 425 365 450 H1300"/><path d="M-60 450 H1300"/><path d="M-60 580 C150 575 175 475 365 450 H1300"/><path d="M-60 710 C155 685 135 495 365 450 H1300"/><path d="M-60 845 C185 815 90 510 365 450 H1300"/></svg>
        {[["Request","flow-request"],["Acknowledge","flow-acknowledge"],["Discover","flow-discover"],["Secure","flow-secure"],["Investigate","flow-investigate"],["Approve","flow-approve"],["Operate","flow-operate"],["Verify","flow-verify"]].map(([label,className]) => <span key={label} className={`auth-flow-node ${className}`}><i/>{label}</span>)}
      </div>
      <div className="public-auth-shell">
        <section className="auth-value"><div className="auth-identity"><OpsLogo/><strong>OpsAgent One</strong><span>{BRAND_TAGLINE}</span></div></section>
        <section className={`login-card public-auth-card ${signupMode ? "is-signup" : "is-login"}`}>
          <div className="auth-mode-tabs"><button className={signupMode ? "active" : ""} onClick={() => { setSignupMode(true); setError(""); }}>Sign up</button><button className={!signupMode ? "active" : ""} onClick={() => { setSignupMode(false); setError(""); }}>Log in</button></div>
          <div className="auth-sso">{authProviders.map(({ id, label, icon: ProviderIcon }) => { const provider = providers.find((item) => item.id === id); return provider?.configured ? <a className={`provider-${id}`} key={id} href={apiUrl(`/auth/oauth/${id}/start`)}><ProviderIcon/> {label}</a> : <button className={`provider-${id}`} key={id} disabled title={`${label} authentication is not configured`}><ProviderIcon/> {label}<small>Setup required</small></button>; })}</div><div className="login-divider"><span>or continue with credentials</span></div>
          {signupMode ? <form className="signup-form" onSubmit={submitSignup}><label>User ID<input value={signupForm.username} onChange={(e) => setSignupForm({...signupForm, username:e.target.value})} autoFocus placeholder="Choose your user ID" required/></label><label>Password<input type="password" value={signupForm.password} onChange={(e) => setSignupForm({...signupForm, password:e.target.value})} placeholder="Minimum 12 characters" required/></label><label>Country<select value={signupForm.country} onChange={(e) => setSignupForm({...signupForm, country:e.target.value})}><option>India</option><option>United States</option><option>United Kingdom</option><option>Canada</option><option>Australia</option><option>Singapore</option><option>United Arab Emirates</option></select></label><label>Mobile number<input type="tel" value={signupForm.mobile_number} onChange={(e) => setSignupForm({...signupForm, mobile_number:e.target.value})} placeholder="Include country code" required/></label>{error && <p className="error">{error}</p>}<button disabled={busy}>{busy ? "Creating account…" : "Create account"}</button></form> : <form onSubmit={submit}><label>Username or business email<input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus placeholder="name@company.com"/></label><label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password"/></label>{error && <p className="error">{error}</p>}<button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button></form>}
          <div className="auth-help">{signupMode ? <button type="button" onClick={() => { setSignupMode(false); setError(""); }}>Already registered? Sign in</button> : <span/>}{!signupMode && <button type="button">Forgot password?</button>}</div><small className="login-trust"><ShieldCheck/> Protected by tenant-scoped access controls</small>
        </section>
      </div>
      <footer>© 2026 OpsAgent One · Security · Privacy</footer>
    </main>
  );
  if (publicDocsOpen) return (
    <main className="public-docs-view">
      <nav className="public-docs-nav">
        <button onClick={closePublicDocs} className="public-brand"><BrandLockup compact /></button>
        <div className="public-docs-links"><button onClick={() => openPublicSection("#product-os")}>Products <ChevronDown/></button><button onClick={() => openPublicSection("#integrations")}>Integrations</button><button className="active">Documentation</button><button onClick={(event) => { closePublicDocs(); openDemo(event); }}>Book a demo</button></div>
        <button className="public-docs-signin" onClick={() => { setPublicDocsOpen(false); setAuthPageOpen(true); history.pushState(null, "", "#signin"); }}>Sign in</button>
      </nav>
      <div className="public-docs-body"><Documentation /></div>
    </main>
  );
  return (
    <main className="public-site public-home">
      <nav className="public-nav">
        <a className="public-brand" href="#top"><BrandLockup compact /></a>
        <div className="public-links"><div className="product-menu"><button>Products <ChevronDown /></button><div className="product-menu-panel enterprise-product-menu product-platform-mega"><header><div><strong>OpsAgent One Platform</strong><span>AI infrastructure operations</span></div><a href="#capabilities">Explore the platform <ChevronRight/></a></header><div className="product-mega-columns">{productMegaGroups.map((group)=><section key={group.title}><h4>{group.title}</h4>{group.items.map(({name,description,icon:ProductIcon,href})=><a key={name} href={href} onClick={href==="#documentation"?openPublicDocs:undefined}><i><ProductIcon/></i><span><b>{name}</b><small>{description}</small></span></a>)}</section>)}</div><footer><span><ShieldCheck/> Built for tenant-scoped enterprise operations</span><a href="#book-demo" onClick={openDemo}>Get a demo <ChevronRight/></a></footer></div></div><a href="#integrations">Integrations</a><a href="#documentation" onClick={openPublicDocs}>Documentation</a><a href="#book-demo" onClick={openDemo}>Book a demo</a></div>
        <div className="public-actions"><a className="nav-signin" href="#signin" onClick={openAuthPage}>Sign in</a></div>
      </nav>
      <section className="public-hero" id="top">
        <div className="hero-word-cloud" aria-hidden="true">
          <div className="word-track"><span>discover</span><i>·</i><span>request</span><i>·</i><span>acknowledge</span><i>·</i><span>investigate</span><i>·</i><span>approve</span><i>·</i><span>operate</span><i>·</i><span>verify</span><i>·</i><span>secure</span><i>·</i><span>discover</span><i>·</i><span>request</span></div>
          <div className="word-track reverse"><span>human controlled</span><i>·</i><span>govern change</span><i>·</i><span>reduce downtime</span><i>·</i><span>verify results</span><i>·</i><span>secure operations</span><i>·</i><span>human controlled</span><i>·</i><span>govern change</span></div>
          <div className="word-track slow"><span>monitor</span><i>·</i><span>acknowledge</span><i>·</i><span>diagnose</span><i>·</i><span>approve</span><i>·</i><span>remediate</span><i>·</i><span>audit</span><i>·</i><span>monitor</span><i>·</i><span>acknowledge</span><i>·</i><span>diagnose</span></div>
          <div className="word-track reverse slow"><span>AWS</span><i>·</i><span>Azure</span><i>·</i><span>VMware</span><i>·</i><span>Windows</span><i>·</i><span>Linux</span><i>·</i><span>SCCM</span><i>·</i><span>Intune</span><i>·</i><span>AWS</span><i>·</i><span>Azure</span></div>
        </div>
        <div className="hero-copy">
          <span className="launch-pill"><Sparkles /> AI INFRASTRUCTURE OPERATIONS PLATFORM</span>
          <h1 className="kinetic-title"><span className="kinetic-line"><b>AI</b><span className="kinetic-window" aria-live="polite" aria-label="discover, request, acknowledge, investigate, approve, operate, verify and secure"><span className="kinetic-words"><i key={heroWords[heroWordIndex]} className={`motion-${heroWordIndex % 3}`}>{heroWords[heroWordIndex]}</i></span></span><b>with</b></span><em>Infrastructure Intelligence</em></h1>
          <p>Every cloud. Every server. Every signal. One intelligent place to discover your estate, govern change, secure operations and scale automation.</p>
          <div className="hero-platform-action"><a href="#demo"><Play /> See the platform</a><span>A quick end-to-end product glimpse</span></div>
        </div>
      </section>
      <section className="integration-strip" id="integrations"><span>DESIGNED TO CONNECT ACROSS YOUR COMPLETE OPERATIONS ESTATE</span><div className="estate-platforms"><div className="estate-track">{[...platformLogos, ...platformLogos].map((item, index) => <b data-brand={item.brand} key={`${item.brand}-${index}`} aria-hidden={index >= platformLogos.length}><span className={`platform-logo ${item.brand === "azure" ? "azure-mark" : ""}`}>{item.logo}</span><small>{item.category}</small><span className="platform-name">{item.name}</span></b>)}</div></div></section>
      <section className="public-integration-guide" id="integration-guide">
        <div className="public-guide-heading"><div><span className="section-kicker">INTEGRATION GUIDE</span><h2>Connect your environment.<br />Keep credentials under your control.</h2></div><p>Use one customer-side connector and least-privilege identities to bring infrastructure into OpsAgent. These are the same stages used for the working AWS, Windows and SCCM lab.</p></div>
        <div className="public-guide-cards">
          <article><header><FaAws/><b>01</b></header><h3>AWS and IAM</h3><p>Create an OpsAgent cross-account role for each customer. Attach <code>AmazonSSMManagedInstanceCore</code> to EC2 instances, tag approved targets <code>OpsAgentManaged=true</code>, and restrict commands to <code>OpsAgent-*</code> documents.</p><small>IAM role → EC2 tags → SSM permission → inventory sync</small></article>
          <article><header><FaWindows/><b>02</b></header><h3>Windows and SSM</h3><p>Install and start Amazon SSM Agent, allow outbound HTTPS to regional SSM endpoints, and confirm every server is Online in Fleet Manager. Operations require explicit approval and return verified command output.</p><small>Agent health → managed node → approved runbook → audit</small></article>
          <article><header><FaMicrosoft/><b>03</b></header><h3>SCCM inventory</h3><p>Run the customer connector on the SCCM site server. The fixed read-only <code>OpsAgent-sccm_inventory</code> document collects devices, collections, deployments and software-update groups without exposing SCCM credentials to the browser.</p><small>Site server → SSM document → SCCM PowerShell → OpsAgent</small></article>
          <article><header><ShieldCheck/><b>04</b></header><h3>WSUS and patching</h3><p>Add the Software Update Point, synchronize only managed Windows Server products, and deploy through Test, Pilot and Production collections with change approval, stakeholder notification and post-patch validation.</p><small>KB intake → test → approve → deploy → verify</small></article>
        </div>
        <div className="public-guide-flow"><span>Customer network</span><ChevronRight/><span>OpsAgent connector</span><ChevronRight/><span>AWS · Windows · SCCM</span><ChevronRight/><span>Verified audit evidence</span></div>
        <a className="public-guide-cta" href="#documentation" onClick={openPublicDocs}>Open the complete public documentation <ChevronRight/></a>
      </section>
      <section className="public-demo" id="demo">
        <div className="demo-heading"><div><span className="section-kicker">SEE THE PLATFORM</span><h2>A simple end-to-end glimpse<br />of OpsAgent at work.</h2></div><p>See how a request enters OpsAgent, gains infrastructure context, moves through approval and finishes with a verified result.</p></div>
        <div className="recorded-demo"><video key={currentDemo.src} autoPlay muted controls playsInline preload="metadata" onEnded={() => setDemoIndex((current) => (current + 1) % demos.length)}><source src={currentDemo.src} type="video/mp4" />Your browser does not support embedded video.</video><div><span>PRODUCT GLIMPSE</span><strong>{currentDemo.label}</strong><small>{currentDemo.flow}</small></div><div className="demo-dots" aria-label="Demo playlist">{demos.map((demo, index) => <button key={demo.src} className={index === demoIndex ? "active" : ""} onClick={() => setDemoIndex(index)} aria-label={`Play ${demo.label}`} />)}</div></div>
      </section>
      <section className="public-section" id="platform"><div className="section-kicker">CONTROL PLANE CAPABILITIES</div><h2>One operational model for<br />hybrid infrastructure.</h2><p className="section-intro">OpsAgent normalizes cloud resources, operating systems, endpoints and telemetry into a tenant-scoped control plane. Deterministic policy remains authoritative for every infrastructure change.</p><div className="public-feature-grid"><article><span className="feature-number">01</span><div className="feature-icon"><Server /></div><h3>Inventory and dependency graph</h3><p>Synchronize AWS, Azure, VMware, Windows, Linux and SCCM inventory with ownership, environment, network, storage and application metadata.</p><a href="#integration-guide">Review connector setup <ChevronRight /></a></article><article><span className="feature-number">02</span><div className="feature-icon"><Database /></div><h3>Telemetry correlation</h3><p>Correlate component health, alerts, logs, asset criticality and recent changes to produce evidence-backed diagnosis and remediation recommendations.</p><a href="#demo">View execution workflow <ChevronRight /></a></article><article><span className="feature-number">03</span><div className="feature-icon"><Activity /></div><h3>Policy-enforced execution</h3><p>Resolve exact targets, require scoped authorization and approval, execute fixed runbooks, verify resulting state and persist request-to-result audit history.</p><a href="#security">Review security controls <ChevronRight /></a></article></div></section>
      <section className="product-detail-pages" aria-label="OpsAgent products">
        <article id="product-os"><div className="product-detail-icon"><MonitorCog/></div><div><span>OPERATING SYSTEM AGENT</span><h2>Govern enterprise operating-system operations.</h2><p>Maintain authoritative server state, collect diagnostic evidence and execute allowlisted runbooks through approval-controlled workflows with verified outcomes.</p><ul><li>Windows and Linux estate intelligence</li><li>Service, process, storage and network lifecycle management</li><li>Policy-controlled remediation with retained audit evidence</li></ul><a href="#capabilities">Explore operating-system capabilities <ChevronRight/></a></div></article>
        <article id="product-cloud"><div className="product-detail-icon"><Cloud/></div><div><span>CLOUD OPERATIONS AGENT</span><h2>One control plane for cloud operations.</h2><p>Connect AWS, Azure and hybrid environments using customer-owned identities, synchronize inventory and perform lifecycle operations without exposing permanent credentials.</p><ul><li>Cloud inventory and resource context</li><li>Provision, start, stop, resize and terminate workflows</li><li>RBAC, MFA, approval and final-state verification</li></ul><a href="#integration-guide">Review cloud connector setup <ChevronRight/></a></div></article>
        <article id="product-patching"><div className="product-detail-icon"><ShieldCheck/></div><div><span>PATCHING AGENT</span><h2>Move every update through a controlled pipeline.</h2><p>Coordinate SCCM, WSUS and endpoint patching from KB intake through test rings, change approval, deployment, compliance and post-patch validation.</p><ul><li>Test, pilot and production rings</li><li>Change and stakeholder approval gates</li><li>Compliance tracking and rollback evidence</li></ul><a href="#capabilities">Explore patching workflows <ChevronRight/></a></div></article>
      </section>
      <section className="capability-explorer" id="capabilities" aria-labelledby="capability-heading">
        <div className="capability-intro"><span className="section-kicker">OPERATIONAL WORKLOADS</span><h2 id="capability-heading">From read-only discovery<br />to verified automation.</h2><p>Each workload uses normalized inventory, connector health, tenant RBAC and an immutable execution trail.</p></div>
        <div className="capability-layout">
          <nav className="capability-tabs" aria-label="OpsAgent capabilities">{capabilities.map((item, index) => { const Icon = item.icon; return <button key={item.title} className={index === capabilityIndex ? "active" : ""} onClick={() => setCapabilityIndex(index)}><Icon /><span>{item.title}</span><ChevronRight /></button>; })}</nav>
          <article className={`capability-panel capability-${capabilityIndex}`}>
            <div className="capability-copy"><span className="capability-icon"><ActiveCapabilityIcon /></span><small>{activeCapability.kicker}</small><h3>{activeCapability.heading}</h3><p>{activeCapability.description}</p><ul>{activeCapability.bullets.map((bullet) => <li key={bullet}><CheckCircle2 />{bullet}</li>)}</ul><a href="#signin" onClick={openAuthPage}>Launch OpsAgent <ChevronRight /></a></div>
            <div className="capability-preview">
              <div className="preview-top"><div><OpsLogo small /><span><b>OpsAgent operational view</b><small>Live enterprise context</small></span></div><i>Connected</i></div>
              <div className="preview-metrics">{activeCapability.metrics.map(([label, value]) => <div key={label}><small>{label}</small><strong>{value}</strong><span /></div>)}</div>
              <div className="preview-chart"><header><b>Operational intelligence</b><span>Last 30 days</span></header><div className="chart-bars"><i style={{height:"42%"}}/><i style={{height:"58%"}}/><i style={{height:"49%"}}/><i style={{height:"76%"}}/><i style={{height:"68%"}}/><i style={{height:"87%"}}/><i style={{height:"94%"}}/></div></div>
              <div className="preview-table"><header><span>Recent evidence</span><span>Status</span></header>{activeCapability.rows.map((row, index) => <div key={row}><span><i />{row}</span><b>{index === 1 && capabilityIndex === 2 ? "Approval required" : "Verified"}</b></div>)}</div>
            </div>
          </article>
        </div>
      </section>
      <section className="always-on-operations">
        <div className="always-on-heading"><div><span className="section-kicker">ORCHESTRATION AND GOVERNANCE</span><h2>Coordinate systems of record<br />without bypassing controls.</h2></div><p>OpsAgent connects monitoring, ITSM, endpoint management and cloud APIs through customer-side connectors. Credentials remain server-side while the control plane manages intent, authorization, approval and evidence.</p></div>
        <div className="operation-outcomes"><div><strong>24/7</strong><span>Infrastructure awareness</span></div><div><strong>Seconds</strong><span>To acknowledge incoming alerts</span></div><div><strong>Approval-gated</strong><span>Human authorization before infrastructure changes</span></div><div><strong>Your model</strong><span>Local or hosted LLM choice</span></div></div>
        <div className="automation-scope"><header><span className="section-kicker">SUPPORTED WORKFLOWS</span><h3>API-driven and approval-gated.</h3></header><div><article><Workflow /><span>01</span><h4>ITSM change orchestration</h4><p>Create Jira or ServiceNow changes containing scope, risk, implementation, rollback, schedule and verification evidence.</p></article><article><MonitorCog /><span>02</span><h4>Patch compliance orchestration</h4><p>Coordinate SCCM/WSUS release intake, test rings, approvals, deployments, compliance tracking and post-patch validation.</p></article><article><Server /><span>03</span><h4>Cloud lifecycle operations</h4><p>Perform scoped AWS, Azure or VMware lifecycle actions through provider identities and resource-level policy.</p></article><article><Boxes /><span>04</span><h4>Configuration runbooks</h4><p>Execute allowlisted Windows, Linux and cloud runbooks with typed parameters, explicit approval and state verification.</p></article><article><Search /><span>05</span><h4>Incident diagnostics</h4><p>Correlate alerts, metrics, logs, dependency state and recent changes to determine likely root cause.</p></article></div></div>
        <div className="operations-detail"><article><MessageSquare /><div><small>MEET TEAMS WHERE THEY WORK</small><h3>Slack, Gmail, Outlook and monitoring tools.</h3><p>Alerts and requests can enter through connected channels. OpsAgent One keeps acknowledgement, approval and completion updates in the same operational conversation.</p></div></article><article><Bot /><div><small>BRING YOUR PREFERRED MODEL</small><h3>Choose quality, privacy and cost.</h3><p>Use local models for private workloads or connect a hosted LLM. Rules and lightweight routing avoid unnecessary model calls, helping control API usage and cost.</p></div></article></div>
      </section>
      <section className="agent-showcase" id="agents"><div className="agent-showcase-copy"><span className="section-kicker">DOMAIN-SPECIFIC AGENTS</span><h2>Specialized reasoning.<br />Deterministic execution.</h2><p>Domain agents can interpret requests and assemble context, but only the policy engine and approved connectors authorize infrastructure changes.</p><div className="agent-list"><span><i className="cyan" />Infrastructure Inventory Agent</span><span><i className="purple" />Patch Orchestration Agent</span><span><i className="blue" />Security Analysis Agent</span><span><i className="green" />Observability Agent</span><span><i className="amber" />Runbook Knowledge Agent</span></div></div><div className="agent-conversation"><div className="conversation-top"><OpsLogo small /><div><strong>OpsAgent</strong><span>Infrastructure operations copilot</span></div><b>Policy connected</b></div><div className="bubble user-bubble">Check OPSAGENT-DC01 and explain any operational risk.</div><div className="bubble ai-bubble"><span><Bot /></span><p><strong>Evidence collected.</strong><br/>The managed node is online, but monitoring ownership is incomplete. No action was executed. A scoped remediation request is ready for operator review.</p></div><div className="conversation-input"><span>Query inventory, health or audit evidence…</span><Send /></div></div></section>
      <section className="security-band" id="security"><div><ShieldCheck /><span>SECURITY ARCHITECTURE</span><h2>Identity, policy and evidence<br />at every boundary.</h2></div><div className="security-points"><article><strong>Tenant-scoped RBAC</strong><p>Organization-aware Owner, Admin, Operator, Approver, Viewer and Auditor authorization.</p></article><article><strong>Least-privilege connectors</strong><p>Cross-account roles, workload identities and allowlisted SSM documents restrict execution scope.</p></article><article><strong>Approval and verification</strong><p>High-impact actions require exact confirmation and resulting infrastructure state is checked after execution.</p></article><article><strong>Persistent audit trail</strong><p>Requester, approver, target, parameters, timestamps, output and verification evidence are retained in PostgreSQL.</p></article></div></section>
      <footer className="public-footer" id="resources"><a className="public-brand" href="#top"><BrandLockup compact /></a><p>{BRAND_TAGLINE}</p><span>© 2026 OpsAgent One</span></footer>
      {demoOpen && <div className="demo-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setDemoOpen(false); }}>
        <section className="demo-modal" role="dialog" aria-modal="true" aria-labelledby="demo-modal-title">
          <button className="demo-modal-close" onClick={() => setDemoOpen(false)} aria-label="Close demo request"><X /></button>
          {demoResult ? <div className="demo-success"><CheckCircle2/><span>REQUEST RECEIVED</span><h2>Thank you—let’s build your operations story.</h2><p>Your reference is <b>{demoResult}</b>. Our team will contact you using the business email provided.</p><button onClick={() => setDemoOpen(false)}>Close</button></div> : <>
            <header><span className="section-kicker">BOOK A PERSONALIZED DEMO</span><h2 id="demo-modal-title">See OpsAgent on your infrastructure use case.</h2><p>Tell us about your environment and we’ll focus the session on the integrations and workflows that matter to your team.</p></header>
            <form onSubmit={submitDemo}>
              <div className="demo-form-grid">
                <label>Full name *<input required minLength={2} value={demoForm.full_name} onChange={(e) => setDemoForm({...demoForm, full_name:e.target.value})} placeholder="Your name" /></label>
                <label>Business email *<input required type="email" value={demoForm.business_email} onChange={(e) => setDemoForm({...demoForm, business_email:e.target.value})} placeholder="name@company.com" /></label>
                <label>Company *<input required minLength={2} value={demoForm.company} onChange={(e) => setDemoForm({...demoForm, company:e.target.value})} placeholder="Company name" /></label>
                <label>Job role<input value={demoForm.job_role} onChange={(e) => setDemoForm({...demoForm, job_role:e.target.value})} placeholder="Infrastructure Manager" /></label>
                <label>Phone<input value={demoForm.phone} onChange={(e) => setDemoForm({...demoForm, phone:e.target.value})} placeholder="Optional" /></label>
                <label>Managed estate<select value={demoForm.estate_size} onChange={(e) => setDemoForm({...demoForm, estate_size:e.target.value})}><option value="">Select size</option><option>1–50 servers</option><option>51–250 servers</option><option>251–1,000 servers</option><option>1,000+ servers</option></select></label>
              </div>
              <fieldset><legend>What would you like to see?</legend><div>{["AWS","Azure","VMware","Windows","Linux","SCCM","Patching","Incident response"].map((interest) => <label key={interest}><input type="checkbox" checked={demoForm.interests.includes(interest)} onChange={(e) => setDemoForm({...demoForm, interests:e.target.checked ? [...demoForm.interests,interest] : demoForm.interests.filter((item)=>item!==interest)})}/>{interest}</label>)}</div></fieldset>
              <label className="demo-message">Anything else we should prepare?<textarea rows={3} value={demoForm.message} onChange={(e) => setDemoForm({...demoForm, message:e.target.value})} placeholder="Current tools, challenges or preferred demo date…" /></label>
              <label className="demo-honeypot" aria-hidden="true">Website<input tabIndex={-1} autoComplete="off" value={demoForm.website} onChange={(e) => setDemoForm({...demoForm, website:e.target.value})}/></label>
              {demoError && <p className="demo-form-error">{demoError}</p>}
              <div className="demo-form-footer"><small>By submitting, you agree that OpsAgent may contact you about this request.</small><button disabled={demoBusy}>{demoBusy ? "Submitting…" : "Request my demo"}<ChevronRight/></button></div>
            </form>
          </>}
        </section>
      </div>}
    </main>
  );
}

function App() {
  // The enterprise workspace is light by default. Set it before the first
  // authenticated render so the asynchronous preference request cannot cause
  // a dark-theme flash during the sign-in transition.
  if (!document.documentElement.dataset.theme) {
    document.documentElement.dataset.theme = "light";
    document.documentElement.dataset.fontSize = "medium";
    document.documentElement.dataset.density = "comfortable";
  }
  const [user, setUser] = useState<User | null>(null);
  const [active, setActive] = useState(() => pageFromPath(location.pathname) || "Dashboard");
  const [sidebarCompact, setSidebarCompact] = useState(() => localStorage.getItem("opsagent_sidebar_compact") === "true");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [servers, setServers] = useState<Machine[]>([]);
  const [health, setHealth] = useState<Health[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [dataConnectionIssue, setDataConnectionIssue] = useState("");
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);
  const navigatePage = (page: string, replace = false) => {
    setActive(page);
    const path = pathForPage(page);
    if (location.pathname !== path) history[replace ? "replaceState" : "pushState"]({ page }, "", path);
  };
  useEffect(() => {
    const restoreRoute = () => setActive(pageFromPath(location.pathname) || "Dashboard");
    window.addEventListener("popstate", restoreRoute);
    return () => window.removeEventListener("popstate", restoreRoute);
  }, []);
  useEffect(() => { if (user && !pageFromPath(location.pathname)) navigatePage(active, true); }, [user]);
  useEffect(() => {
    const match = location.hash.match(/access_token=([^&]+)/);
    if (match) {
      localStorage.setItem("opsagent_token", decodeURIComponent(match[1]));
      history.replaceState(null, "", location.pathname);
    }
  }, []);
  useEffect(() => {
    if (!localStorage.getItem("opsagent_token")) {
      setLoading(false);
      return;
    }
    let disposed = false;
    let restored = false;
    const restoreSession = () => api<User>("/auth/me")
      .then((value) => { if (!disposed) { restored = true; setUser(value); setDataConnectionIssue(""); } })
      .catch((error: Error) => { if (!disposed && localStorage.getItem("opsagent_token")) setDataConnectionIssue(`Control plane unavailable: ${error.message}. Retrying automatically…`); })
      .finally(() => { if (!disposed) setLoading(false); });
    restoreSession();
    const retry = window.setInterval(() => { if (!disposed && !restored && localStorage.getItem("opsagent_token")) restoreSession(); }, 10000);
    return () => { disposed = true; window.clearInterval(retry); };
  }, []);
  useEffect(() => {
    const handleUnauthorized = () => {
      localStorage.removeItem("opsagent_token");
      setUser(null);
    };
    window.addEventListener("opsagent:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("opsagent:unauthorized", handleUnauthorized);
  }, []);
  useEffect(() => {
    if (!user) return;
    let disposed = false;
    const loadWorkspace = async () => {
      const results = await Promise.allSettled([
        api<Summary>("/dashboard/summary"),
        api<Machine[]>("/inventory/servers"),
        api<Health[]>("/agents/health"),
      ]);
      if (disposed) return;
      if (results[0].status === "fulfilled") setSummary(results[0].value);
      if (results[1].status === "fulfilled") setServers(results[1].value);
      if (results[2].status === "fulfilled") setHealth(results[2].value);
      const failed = results.filter((result) => result.status === "rejected");
      setDataConnectionIssue(failed.length ? "Live data is temporarily unavailable. Retrying automatically…" : "");
    };
    loadWorkspace();
    const retry = window.setInterval(loadWorkspace, 15000);
    return () => { disposed = true; window.clearInterval(retry); };
  }, [user]);
  useEffect(() => {
    if (user) api<Preferences>("/settings").then(applyPreferences).catch(() => undefined);
  }, [user]);
  if (loading) return <div className="splash">Loading OpsAgent…</div>;
  if (!user) return <Login onLogin={setUser} />;
  const visible = servers.filter((s) =>
    JSON.stringify(s).toLowerCase().includes(query.toLowerCase()),
  );
  const logout = () => {
    localStorage.removeItem("opsagent_token");
    setUser(null);
    history.replaceState(null, "", "/");
  };
  async function switchOrganization(organizationId: string) {
    const result = await api<{ access_token: string; user: User }>(
      `/iam/switch/${organizationId}`,
      { method: "POST" },
    );
    localStorage.setItem("opsagent_token", result.access_token);
    setUser(result.user);
  }
  return (
    <div className={`shell ${sidebarCompact ? "sidebar-compact" : ""}`}>
      <aside>
        <div className="logo"><BrandLockup compact /></div>
        <button className="sidebar-toggle" onClick={() => setSidebarCompact((current) => { const next = !current; localStorage.setItem("opsagent_sidebar_compact", String(next)); return next; })} title={sidebarCompact ? "Expand navigation" : "Collapse navigation"} aria-label={sidebarCompact ? "Expand navigation" : "Collapse navigation"}>
          {sidebarCompact ? <ChevronsRight /> : <><ChevronsLeft /><span>Collapse navigation</span></>}
        </button>
        <div className="organization">
          <span>ORGANIZATION</span>
          <select
            value={user.organization_id}
            onChange={(e) => switchOrganization(e.target.value)}
          >
            {(user.organizations || []).map((org) => (
              <option value={org.organization_id} key={org.organization_id}>
                {org.name} · {displayRole(org.organization_role)}
              </option>
            ))}
          </select>
        </div>
        <nav>
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <p>{group.label}</p>
              {group.items.map(([label, Icon]) => (
                <button
                  className={active === label ? "active" : ""}
                  onClick={() => navigatePage(label)}
                  key={label}
                  title={sidebarCompact ? label : undefined}
                  aria-label={label}
                >
                  <Icon />
                  <span>{label}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="user">
          {sidebarCompact ? <button className="avatar profile-avatar" onClick={() => setLogoutConfirmOpen(true)} title="Sign out" aria-label="Sign out">
            {user.display_name.slice(0, 2).toUpperCase()}
          </button> : <div className="avatar">
            {user.display_name.slice(0, 2).toUpperCase()}
          </div>}
          <div className="user-identity" title={user.display_name}>
            <strong>{user.display_name}</strong>
            <span>{displayRole(user.organization_role || user.role)}</span>
          </div>
          <button onClick={() => setLogoutConfirmOpen(true)} title="Sign out">
            <LogOut />
          </button>
        </div>
      </aside>
      <main className="workspace">
        <div className="enterprise-bar">
          <div className="breadcrumb">
            <span>OpsAgent One</span>
            <b>/</b>
            <strong>{active}</strong>
          </div>
          <div className="context">
            <button className="global-search" onClick={() => navigatePage("Server inventory")}>
              <Search />
              Search resources
              <kbd>⌘ K</kbd>
            </button>
            <button className="bell" onClick={() => navigatePage("Slack alerts")} title="Open operational alerts">
              <Bell />
            </button>
            <button className="top-profile" onClick={() => navigatePage("Account & access")} title="Account and access">
              {user.display_name.slice(0, 2).toUpperCase()}
            </button>
          </div>
        </div>
        {dataConnectionIssue && <div className="data-connection-banner" role="status"><AlertTriangle/><span>{dataConnectionIssue}</span><button onClick={() => window.location.reload()}>Retry now</button></div>}
        {!(["AWS operations", "Agent orchestration"].includes(active)) && <header className="workspace-heading">
          <div>
            <p className="eyebrow">OPERATIONS CENTER</p>
            <h1>{active}</h1>
            <p className="workspace-description">
              Monitor, investigate and safely operate your hybrid
              infrastructure.
            </p>
          </div>
        </header>}
        <Workspace
          active={active}
          summary={summary}
          servers={visible}
          allServers={servers}
          health={health}
          query={query}
          setQuery={setQuery}
          user={user}
          onNavigate={navigatePage}
        />
      </main>
      {logoutConfirmOpen && <div className="logout-confirm-backdrop" role="presentation" onMouseDown={() => setLogoutConfirmOpen(false)}>
        <section className="logout-confirm" role="dialog" aria-modal="true" aria-labelledby="logout-confirm-title" onMouseDown={(event) => event.stopPropagation()}>
          <div className="logout-confirm-icon"><LogOut /></div>
          <div><span>ACCOUNT SESSION</span><h2 id="logout-confirm-title">Sign out of OpsAgent One?</h2><p>You’ll need to sign in again to access your organization’s operations workspace.</p></div>
          <footer><button onClick={() => setLogoutConfirmOpen(false)}>Cancel</button><button className="confirm-signout" onClick={logout}>Sign out</button></footer>
        </section>
      </div>}
    </div>
  );
}

function Workspace(p: {
  active: string;
  summary: Summary | null;
  servers: Machine[];
  allServers: Machine[];
  health: Health[];
  query: string;
  setQuery: (x: string) => void;
  user: User;
  onNavigate?: (page: string) => void;
}) {
  if (p.active === "Dashboard")
    return (
      <Dashboard summary={p.summary} servers={p.allServers} health={p.health} onNavigate={p.onNavigate} />
    );
  if (p.active === "Server inventory")
    return (
      <Inventory servers={p.allServers} query={p.query} setQuery={p.setQuery} />
    );
  if (p.active === "Decommission inventory") return <DecommissionInventory />;
  if (p.active === "Hardware inventory") return <HardwareInventoryWorkspace onNavigate={p.onNavigate} />;
  if (p.active === "OpsAgent chat") return <Chat />;
  if (p.active === "Service desk agent") return <ServiceDeskWorkspace />;
  if (p.active === "Agent orchestration") return <AgentWorkspace health={p.health} onNavigate={p.onNavigate} />;
  if (p.active === "Connections") return <ConnectionsCenter />;
  if (p.active === "Slack alerts")
    return <AlertOperations channel="slack" health={p.health} />;
  if (p.active === "Gmail alerts")
    return <AlertOperations channel="gmail" health={p.health} />;
  if (p.active === "AWS operations")
    return (
      <AwsOperationsV2
        servers={p.allServers.filter((x) => x.vm_type === "aws" && x.enabled !== false && x.status !== "terminated")}
        user={p.user}
        onNavigate={p.onNavigate}
      />
    );
  if (p.active === "Windows operations") return <WindowsOperations servers={p.allServers.filter((server) => server.enabled !== false && `${server.os_type || ""} ${server.os_version || ""}`.toLowerCase().includes("windows"))} />;
  if (p.active === "Linux operations") return <LinuxOperations servers={p.allServers.filter((server) => server.enabled !== false && `${server.os_type || ""} ${server.os_version || ""}`.toLowerCase().includes("linux"))} />;
  if (p.active === "SCCM operations") return <SccmWorkspace />;
  if (p.active === "Azure operations")
    return <ProviderWorkspace provider="azure" />;
  if (p.active === "VMware operations")
    return <ProviderWorkspace provider="vmware" />;
  if (p.active === "Hardware monitoring") return <HardwareMonitoringWorkspace onNavigate={p.onNavigate} />;
  if (p.active === "Agent health") return <AgentHealthWorkspace health={p.health} />;
  if (p.active === "Live logs")
    return (
      <RemoteWorkspace endpoint="/logs?limit=500" title="Operational logs" />
    );
  if (p.active === "AI usage & cost") return <Usage />;
  if (p.active === "Account & access") return <Account user={p.user} />;
  if (p.active === "Settings") return <SettingsCenter />;
  if (p.active === "Documentation") return <Documentation />;
  return <ComingSoon title={p.active} />;
}

function Dashboard({
  summary,
  servers,
  health,
  onNavigate,
}: {
  summary: Summary | null;
  servers: Machine[];
  health: Health[];
  onNavigate?: (page: string) => void;
}) {
  const [operations, setOperations] = useState<{ summary: Record<string, number>; events: Record<string, unknown>[] } | null>(null);
  const [slack, setSlack] = useState<Record<string, number> | null>(null);
  const [gmail, setGmail] = useState<Record<string, number> | null>(null);
  const [hardware, setHardware] = useState<HardwareDashboard | null>(null);
  const [sccmDashboard, setSccmDashboard] = useState<SccmInventory | null>(null);
  const [logs, setLogs] = useState<Record<string, unknown>[]>([]);
  const [refreshing, setRefreshing] = useState(true);
  const [loadIssues, setLoadIssues] = useState<string[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [platformChart, setPlatformChart] = useState<"pie" | "bar">("pie");
  const [channelChart, setChannelChart] = useState<"pie" | "bar">("pie");
  const [healthChart, setHealthChart] = useState<"pie" | "bar">("pie");
  const [hardwareChart, setHardwareChart] = useState<"pie" | "bar">("pie");
  const [osChart, setOsChart] = useState<"pie" | "bar">("pie");
  const [windowsVersionChart, setWindowsVersionChart] = useState<"pie" | "bar">("bar");
  const [linuxVersionChart, setLinuxVersionChart] = useState<"pie" | "bar">("bar");
  const [sccmChart, setSccmChart] = useState<"pie" | "bar">("bar");
  const [virtualizationChart, setVirtualizationChart] = useState<"pie" | "bar">("pie");
  const [vmwareVersionChart, setVmwareVersionChart] = useState<"pie" | "bar">("bar");
  const [hardwareTypeChart, setHardwareTypeChart] = useState<"pie" | "bar">("pie");
  const [powerChart, setPowerChart] = useState<"pie" | "bar">("pie");
  const [environmentChart, setEnvironmentChart] = useState<"pie" | "bar">("pie");
  const [monitoringChart, setMonitoringChart] = useState<"pie" | "bar">("pie");
  const [changeChart, setChangeChart] = useState<"pie" | "bar">("pie");
  const loadDashboard = async () => {
    setRefreshing(true);
    const results = await Promise.allSettled([
      api<{ summary: Record<string, number>; events: Record<string, unknown>[] }>("/operations/aws/audit?hours=24"),
      api<{ summary: Record<string, number> }>("/alerts/slack?hours=24"),
      api<{ summary: Record<string, number> }>("/alerts/gmail?hours=24"),
      api<Record<string, unknown>[]>("/logs?limit=8"),
      api<HardwareDashboard>("/hardware/dashboard"),
      api<SccmInventory>("/sccm/inventory"),
    ]);
    const [awsResult, slackResult, gmailResult, logResult, hardwareResult, sccmResult] = results;
    if (awsResult.status === "fulfilled") setOperations(awsResult.value);
    if (slackResult.status === "fulfilled") setSlack(slackResult.value.summary);
    if (gmailResult.status === "fulfilled") setGmail(gmailResult.value.summary);
    if (logResult.status === "fulfilled") setLogs(logResult.value);
    if (hardwareResult.status === "fulfilled") setHardware(hardwareResult.value);
    if (sccmResult.status === "fulfilled") setSccmDashboard(sccmResult.value);
    const names = ["Change audit", "Slack", "Gmail", "Operational logs", "Hardware", "SCCM"];
    setLoadIssues(results.flatMap((result, index) => result.status === "rejected" ? [names[index]] : []));
    setLastUpdated(new Date());
    setRefreshing(false);
  };
  useEffect(() => {
    loadDashboard();
    const timer = window.setInterval(loadDashboard, 60000);
    return () => window.clearInterval(timer);
  }, []);
  if (!summary) return <div className="skeleton">Loading live estate…</div>;
  const unowned = servers.filter((s) => !s.server_team && !s.application_team).length;
  const unmonitored = servers.filter((s) => !s.monitoring_service || /unknown|not assigned/i.test(s.monitoring_service)).length;
  const publicAssets = servers.filter((s) => s.public_ip_address).length;
  const healthy = health.filter((x) => x.Status === "Healthy").length;
  const coverage = health.length ? Math.round((healthy / health.length) * 100) : 0;
  const availability = summary.total ? Math.round((summary.powered_on / summary.total) * 100) : 0;
  const maxProvider = Math.max(1, ...Object.values(summary.providers));
  const findings = [
    ["Powered-off assets", summary.powered_off, "Unavailable or intentionally stopped", summary.powered_off ? "medium" : "good", Activity],
    ["Ownership gaps", unowned, "No accountable team assigned", unowned ? "high" : "good", Users],
    ["Monitoring gaps", unmonitored, "No monitoring service recorded", unmonitored ? "high" : "good", Eye],
    ["Publicly addressed", publicAssets, "Assets with a public IP address", publicAssets ? "medium" : "good", AlertTriangle],
  ] as const;
  const operationTotal = operations?.summary.total;
  const operationFailed = operations?.summary.failed;
  const outstandingAlerts = slack?.outstanding;
  const connectorProblems = health.filter((item) => item.Status !== "Healthy");
  const grafanaHealth = health.find((item) => /grafana/i.test(item.Component));
  const monitored = Math.max(0, servers.length - unmonitored);
  const monitoringCoverage = servers.length ? Math.round(monitored / servers.length * 100) : 0;
  const safeHealthDetail = (item: Health) => {
    const detail = String(item.Details || item["Last heartbeat"] || "No recent health detail");
    if (/main thread|interpreter|traceback|exception|timed out/i.test(detail)) return "Connector worker requires attention";
    return detail;
  };
  const openIntegrationGuide = () => {
    sessionStorage.setItem("opsagent_docs_section", "Integration runbook");
    onNavigate?.("Documentation");
  };
  const providerSeries = Object.entries(summary.providers).map(([label, value], index) => ({ label: label.toUpperCase(), value, color: ["#f59e0b", "#268bd2", "#7357d9", "#17a673"][index % 4] }));
  const channelSeries = [
    { label: "Slack", value: slack?.received || 0, color: "#611f69" },
    { label: "Gmail", value: gmail?.received || 0, color: "#ea4335" },
  ];
  const healthSeries = [
    { label: "Healthy", value: healthy, color: "#18a66a" },
    { label: "Needs attention", value: connectorProblems.length, color: "#e58b2a" },
  ];
  const hardwareSeries = [
    { label: "Cisco", value: hardware?.summary.vendors.Cisco || 0, color: "#1585cf" },
    { label: "Dell", value: hardware?.summary.vendors.Dell || 0, color: "#0672ce" },
    { label: "HPE", value: hardware?.summary.vendors.HPE || hardware?.summary.vendors.HP || 0, color: "#01a982" },
    { label: "Other", value: Object.entries(hardware?.summary.vendors || {}).filter(([name]) => !/^(cisco|dell|hpe|hp)$/i.test(name)).reduce((sum, [, value]) => sum + value, 0), color: "#7b61d1" },
  ];
  const osCount = (pattern: RegExp) => servers.filter((server) => pattern.test(`${server.os_type || ""} ${server.os_version || ""}`)).length;
  const osSeries = [
    { label: "Windows", value: osCount(/windows/i), color: "#1674d1" },
    { label: "Linux", value: osCount(/linux|ubuntu|rhel|red hat|centos|suse|debian/i), color: "#e0a11b" },
    { label: "Unix / AIX", value: osCount(/unix|aix|solaris/i), color: "#7157d9" },
    { label: "Other / unknown", value: servers.filter((server) => !/windows|linux|ubuntu|rhel|red hat|centos|suse|debian|unix|aix|solaris/i.test(`${server.os_type || ""} ${server.os_version || ""}`)).length, color: "#93a0b2" },
  ];
  const versionSeries = (matcher: RegExp, fallback: string) => {
    const counts = servers.filter((server) => matcher.test(`${server.os_type || ""} ${server.os_version || ""}`)).reduce<Record<string, number>>((result, server) => {
      const label = String(server.os_version || fallback).trim() || fallback;
      result[label] = (result[label] || 0) + 1;
      return result;
    }, {});
    const colors = ["#1674d1","#18a66a","#e0a11b","#7157d9","#e85b68","#168ea1","#68778b","#a5673f"];
    const values = Object.entries(counts).sort((a,b) => b[1] - a[1]).slice(0,8).map(([label,value],index) => ({label,value,color:colors[index]}));
    return values.length ? values : [{label:`No ${fallback} data`,value:0,color:"#93a0b2"}];
  };
  const windowsVersionSeries = versionSeries(/windows/i, "Windows version unknown");
  const linuxVersionSeries = versionSeries(/linux|ubuntu|rhel|red hat|centos|suse|debian/i, "Linux version unknown");
  const sccmSeries = [
    { label: "Devices", value: sccmDashboard?.summary.devices || 0, color: "#315eea" },
    { label: "Active clients", value: sccmDashboard?.summary.active_clients || 0, color: "#18a66a" },
    { label: "Collections", value: sccmDashboard?.summary.collections || 0, color: "#7b61d1" },
    { label: "Deployments", value: sccmDashboard?.summary.deployments || 0, color: "#e58b2a" },
    { label: "Update groups", value: sccmDashboard?.summary.update_groups || 0, color: "#168ea1" },
  ];
  const virtualizationSeries = [
    { label: "VMware VMs", value: servers.filter((server) => /vmware|vsphere/i.test(server.vm_type || "") && !/esxi/i.test(`${server.vm_type} ${server.os_type}`)).length, color: "#6075d8" },
    { label: "ESXi hosts", value: servers.filter((server) => /esxi/i.test(`${server.vm_type} ${server.os_type} ${server.os_version}`)).length, color: "#18a66a" },
    { label: "Hyper-V", value: servers.filter((server) => /hyper.?v/i.test(`${server.vm_type} ${server.os_type}`)).length, color: "#1674d1" },
    { label: "Nutanix", value: servers.filter((server) => /nutanix|ahv/i.test(`${server.vm_type} ${server.os_type}`)).length, color: "#e58b2a" },
  ];
  const vmwareVersionCounts = servers.filter((server) => /vmware|vsphere|esxi/i.test(`${server.vm_type} ${server.os_type} ${server.os_version}`)).reduce<Record<string,number>>((result,server) => {
    const label = String(server.os_version || (/esxi/i.test(`${server.vm_type} ${server.os_type}`) ? "ESXi version unknown" : "VMware version unknown"));
    result[label] = (result[label] || 0) + 1; return result;
  },{});
  const vmwareVersionSeries = Object.entries(vmwareVersionCounts).map(([label,value],index)=>({label,value,color:["#6075d8","#18a66a","#e58b2a","#7b61d1","#168ea1"][index%5]}));
  if (!vmwareVersionSeries.length) vmwareVersionSeries.push({label:"No VMware version data",value:0,color:"#93a0b2"});
  const hardwareTypeSeries = Object.entries(hardware?.summary.types || {}).map(([label,value],index)=>({label,value,color:["#315eea","#18a66a","#e58b2a","#7b61d1","#168ea1"][index%5]}));
  if (!hardwareTypeSeries.length) hardwareTypeSeries.push({label:"No hardware connected",value:0,color:"#93a0b2"});
  const powerSeries = [
    {label:"Powered on",value:summary.powered_on,color:"#18a66a"},
    {label:"Powered off",value:summary.powered_off,color:"#e58b2a"},
    {label:"Unknown",value:summary.unknown,color:"#93a0b2"},
  ];
  const environmentSeries = [
    {label:"Production",value:summary.production,color:"#315eea"},
    {label:"Test / QA",value:summary.test,color:"#7b61d1"},
    {label:"Unknown",value:summary.unknown,color:"#93a0b2"},
  ];
  const monitoringSeries = [
    {label:"Monitored",value:monitored,color:"#18a66a"},
    {label:"Monitoring gap",value:unmonitored,color:"#e85b68"},
  ];
  const changeSeries = [
    {label:"Succeeded",value:operations?.summary.succeeded || 0,color:"#18a66a"},
    {label:"Failed",value:operations?.summary.failed || 0,color:"#e85b68"},
    {label:"Unknown",value:operations?.summary.unknown || 0,color:"#93a0b2"},
  ];
  const pieBackground = (series: { value: number; color: string }[]) => {
    const total = series.reduce((sum, item) => sum + item.value, 0);
    if (!total) return "conic-gradient(#dfe6ee 0 100%)";
    let offset = 0;
    return `conic-gradient(${series.map((item) => { const start = offset; offset += item.value / total * 100; return `${item.color} ${start}% ${offset}%`; }).join(",")})`;
  };
  const chartPanel = (title: string, kicker: string, mode: "pie" | "bar", setMode: (value: "pie" | "bar") => void, series: { label: string; value: number; color: string }[], action: () => void) => {
    const total = series.reduce((sum, item) => sum + item.value, 0);
    const maximum = Math.max(1, ...series.map((item) => item.value));
    return <article className="command-panel dashboard-chart-panel"><header><div><span>{kicker}</span><h3>{title}</h3></div><div className="chart-header-actions"><div className="chart-switch" aria-label={`${title} visualization`}><button className={mode === "pie" ? "active" : ""} onClick={() => setMode("pie")}>Pie</button><button className={mode === "bar" ? "active" : ""} onClick={() => setMode("bar")}>Bar</button></div><button onClick={action}>View details <ChevronRight /></button></div></header><div className={`dashboard-chart ${mode}`}>
      {mode === "pie" ? <div className="pie-layout"><div className="pie-chart" style={{background:pieBackground(series)}}><div><strong>{total}</strong><span>Total</span></div></div><div className="chart-legend">{series.map((item)=><div key={item.label}><i style={{background:item.color}}/><span>{item.label}</span><strong>{item.value}</strong><small>{total ? `${Math.round(item.value / total * 100)}%` : "0%"}</small></div>)}</div></div> : <div className="dashboard-bars">{series.map((item)=><div key={item.label}><div><span>{item.label}</span><strong>{item.value}</strong></div><i><b style={{width:`${item.value / maximum * 100}%`,background:item.color}}/></i></div>)}</div>}
    </div></article>;
  };
  return (
    <section className="command-dashboard">
      <section className="command-heading"><div><span>OPERATIONS COMMAND CENTER</span><h2>Infrastructure operations at a glance</h2><p>Live estate health, alerts, changes and connector readiness.</p><small className={loadIssues.length ? "dashboard-freshness degraded" : "dashboard-freshness"}><i />{loadIssues.length ? `Partial data · ${loadIssues.join(", ")} unavailable` : `Live data · updated ${lastUpdated ? lastUpdated.toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"}) : "now"}`}</small></div><div><button className="icon-action" onClick={loadDashboard} disabled={refreshing} title="Refresh dashboard"><RefreshCw className={refreshing ? "spin" : ""}/></button><button className="secondary-action" onClick={() => onNavigate?.("Server inventory")}><Server /> View inventory</button><button className="primary-action" onClick={() => onNavigate?.("OpsAgent chat")}><Sparkles /> Ask OpsAgent</button></div></section>

      <section className="command-kpis">
        <article><div><span>Estate availability</span><small>{summary.powered_on} of {summary.total} assets active</small></div><strong>{availability}%</strong><i className="kpi-line"><b style={{width:`${availability}%`}} /></i></article>
        <article><div><span>Outstanding alerts</span><small>Slack alerts requiring action</small></div><strong className={outstandingAlerts ? "attention" : ""}>{outstandingAlerts ?? "—"}</strong></article>
        <article><div><span>Changes</span><small>Operations executed in 24 hours</small></div><strong>{operationTotal ?? "—"}</strong></article>
        <article><div><span>Control health</span><small>{healthy} healthy · {connectorProblems.length} need attention</small></div><strong>{coverage}%</strong><i className="kpi-line"><b style={{width:`${coverage}%`}} /></i></article>
      </section>

      <section className="dashboard-visuals">
        {chartPanel("Assets by platform", "ESTATE COVERAGE", platformChart, setPlatformChart, providerSeries, () => onNavigate?.("Server inventory"))}
        {chartPanel("Alert requests by channel", "REQUEST CHANNELS", channelChart, setChannelChart, channelSeries, () => onNavigate?.("Slack alerts"))}
        {chartPanel("Control-plane health", "SERVICE READINESS", healthChart, setHealthChart, healthSeries, () => onNavigate?.("Agent health"))}
        {chartPanel("Hardware estate", `HARDWARE HEALTH · ${hardware?.summary.active_alerts || 0} OPEN FINDINGS`, hardwareChart, setHardwareChart, hardwareSeries, () => onNavigate?.("Hardware monitoring"))}
        {chartPanel("Operating systems", "SERVER ESTATE", osChart, setOsChart, osSeries, () => onNavigate?.("Server inventory"))}
        {chartPanel("Windows versions", "WINDOWS SERVER ESTATE", windowsVersionChart, setWindowsVersionChart, windowsVersionSeries, () => onNavigate?.("Windows operations"))}
        {chartPanel("Linux versions", "LINUX DISTRIBUTIONS AND RELEASES", linuxVersionChart, setLinuxVersionChart, linuxVersionSeries, () => onNavigate?.("Linux operations"))}
        {chartPanel("SCCM estate", "ENDPOINT AND PATCHING", sccmChart, setSccmChart, sccmSeries, () => onNavigate?.("SCCM operations"))}
        {chartPanel("Virtualization estate", "VMWARE · ESXI · HYPER-V · NUTANIX", virtualizationChart, setVirtualizationChart, virtualizationSeries, () => onNavigate?.("VMware operations"))}
        {chartPanel("VMware and ESXi versions", "VIRTUALIZATION VERSIONS", vmwareVersionChart, setVmwareVersionChart, vmwareVersionSeries, () => onNavigate?.("VMware operations"))}
        {chartPanel("Hardware by type", "CHASSIS · BLADES · RACK SERVERS", hardwareTypeChart, setHardwareTypeChart, hardwareTypeSeries, () => onNavigate?.("Hardware inventory"))}
        {chartPanel("Asset power state", "AVAILABILITY", powerChart, setPowerChart, powerSeries, () => onNavigate?.("Server inventory"))}
        {chartPanel("Assets by environment", "PRODUCTION · TEST · UNKNOWN", environmentChart, setEnvironmentChart, environmentSeries, () => onNavigate?.("Server inventory"))}
        {chartPanel("Monitoring coverage", "OBSERVABILITY", monitoringChart, setMonitoringChart, monitoringSeries, () => onNavigate?.("Agent health"))}
        {chartPanel("Change outcomes", "LAST 24 HOURS", changeChart, setChangeChart, changeSeries, () => onNavigate?.("AWS operations"))}
      </section>

      <section className="command-grid primary-grid">
        <article className="command-panel priority-panel"><header><div><span>ACTION REQUIRED</span><h3>Prioritized operational risks</h3></div><button onClick={() => onNavigate?.("Server inventory")}>Investigate <ChevronRight /></button></header>{findings.map(([label,count,detail,severity,Icon])=><button className="risk-row" key={label} onClick={()=>onNavigate?.(label === "Monitoring gaps" ? "Agent health" : label === "Publicly addressed" ? "AWS operations" : "Server inventory")}><i className={`risk-icon ${severity}`}><Icon /></i><div><strong>{label}</strong><small>{detail}</small></div><b>{count}</b><ChevronRight /></button>)}</article>
        <article className="command-panel estate-panel"><header><div><span>ESTATE COVERAGE</span><h3>Assets by platform</h3></div><b>{summary.total} total</b></header><div className="source-bars">{Object.entries(summary.providers).map(([name,count])=><div className="source-bar" key={name}><div><span className={`source-dot ${name}`} /><strong>{name.toUpperCase()}</strong><b>{count}</b></div><div className="bar-track"><i style={{width:`${count/maxProvider*100}%`}} /></div></div>)}</div><footer><div><strong>{summary.production}</strong><span>Production</span></div><div><strong>{summary.test}</strong><span>Test / QA</span></div><div><strong>{summary.unknown}</strong><span>Unknown</span></div></footer></article>
      </section>

      <section className="command-grid status-grid">
        <article className="command-panel channel-panel"><header><div><span>REQUEST CHANNELS</span><h3>Alert and request processing</h3></div><button onClick={() => onNavigate?.("Slack alerts")}>Open alerts <ChevronRight /></button></header><div className="channel-summary"><button onClick={()=>onNavigate?.("Slack alerts")}><FaSlack/><span>Slack</span><strong>{slack?.received ?? "—"}</strong><small>received</small><b>{slack?.average_ack_seconds != null ? `${slack.average_ack_seconds}s avg ack` : "No response data"}</b></button><button onClick={()=>onNavigate?.("Gmail alerts")}><SiGmail/><span>Gmail</span><strong>{gmail?.received ?? "—"}</strong><small>received</small><b>{gmail?.processed ?? "—"} processed</b></button><button onClick={()=>onNavigate?.("AWS operations")}><ShieldCheck/><span>Changes</span><strong>{operations?.summary.succeeded ?? "—"}</strong><small>succeeded</small><b className={operationFailed ? "failed" : ""}>{operationFailed ?? "—"} failed</b></button></div></article>
        <article className="command-panel connector-panel"><header><div><span>CONTROL PLANE</span><h3>Connector and service health</h3></div><button onClick={() => onNavigate?.("Agent health")}>All services <ChevronRight /></button></header><div className="connector-list">{health.slice(0,6).map((item)=><button key={item.Component} onClick={()=>onNavigate?.("Agent health")}><i className={item.Status.toLowerCase()} /><span><strong>{item.Component}</strong><small>{safeHealthDetail(item)}</small></span><b>{item.Status}</b></button>)}</div></article>
      </section>

      <section className="command-panel observability-panel">
        <header><div><span>OBSERVABILITY POSTURE</span><h3>Monitoring coverage and signal readiness</h3></div><button onClick={() => onNavigate?.("Connections")}>Manage integrations <ChevronRight /></button></header>
        <div className="observability-grid"><article><div className="observability-ring" style={{"--coverage":`${monitoringCoverage * 3.6}deg`} as React.CSSProperties}><span><strong>{monitoringCoverage}%</strong><small>covered</small></span></div><div><b>Infrastructure monitoring</b><p>{monitored} of {servers.length} assets have an assigned monitoring service.</p></div></article><article><SiGrafana/><div><b>Grafana signal pipeline</b><p>{grafanaHealth ? safeHealthDetail(grafanaHealth) : "No Grafana health signal has been registered."}</p></div><span className={grafanaHealth?.Status === "Healthy" ? "status-good" : "status-warn"}>{grafanaHealth?.Status || "Not connected"}</span></article><article><Activity/><div><b>Open operational signals</b><p>Outstanding requests that still require acknowledgement or investigation.</p></div><strong>{outstandingAlerts ?? "—"}</strong></article><article><CheckCircle2/><div><b>Change success rate</b><p>Verified AWS operations completed during the last 24 hours.</p></div><strong>{operationTotal ? `${Math.round(((operations?.summary.succeeded || 0) / operationTotal) * 100)}%` : "—"}</strong></article></div>
      </section>

      <section className="command-panel integration-guide-panel">
        <header><div><span>IMPLEMENTATION GUIDE</span><h3>Connect and operate your infrastructure</h3></div><button onClick={openIntegrationGuide}>Open full guide <ChevronRight /></button></header>
        <p>Repeat the proven setup used in this environment—from cloud identity and managed nodes through SCCM inventory, WSUS synchronization and approval-gated patching.</p>
        <div className="integration-guide-grid">
          <button onClick={openIntegrationGuide}><FaAws/><span><strong>AWS and IAM</strong><small>Cross-account access, instance roles, tags and guarded SSM permissions</small></span><b>01</b></button>
          <button onClick={openIntegrationGuide}><FaWindows/><span><strong>Windows and SSM</strong><small>Register Windows servers, verify agent health and run approved documents</small></span><b>02</b></button>
          <button onClick={openIntegrationGuide}><FaMicrosoft/><span><strong>SCCM and WSUS</strong><small>Inventory connector, SUP configuration, products, classifications and sync</small></span><b>03</b></button>
          <button onClick={openIntegrationGuide}><ShieldCheck/><span><strong>Patch pipeline</strong><small>Test ring, approvals, deployment status, validation, email and audit</small></span><b>04</b></button>
        </div>
      </section>

      <section className="command-panel timeline-panel"><header><div><span>RECENT ACTIVITY</span><h3>Operational event timeline</h3></div><button onClick={() => onNavigate?.("Live logs")}>View live logs <ChevronRight /></button></header>{logs.length ? <div className="timeline-list">{logs.slice(0,6).map((log,index)=><div key={index}><i className={String(log.Level || "info").toLowerCase()} /><span><strong>{String(log.Event || "Operational event").replaceAll("_"," ")}</strong><small>{String(log.Component || "OpsAgent")} · {String(log.Details || "No additional details")}</small></span><time>{String(log.Time || "")}</time></div>)}</div> : <div className="dashboard-empty">No recent operational events recorded.</div>}</section>
    </section>
  );
}
function DecommissionInventory() {
  const [records, setRecords] = useState<Record<string, unknown>[]>([]);
  const [inventoryState, setInventoryState] = useState({total:0,off:0,aws:0});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState("all");
  const [expanded, setExpanded] = useState<Set<string>>(new Set(["cloud", "aws", "azure", "onprem", "vmware", "vmware:vms", "physical", "hardware"]));
  const [selectedName, setSelectedName] = useState("");
  const load = async (synchronizeAws = false) => {
    setLoading(true); setError("");
    try {
      if (synchronizeAws) await api("/connections/aws/sync", {method:"POST"});
      const servers = await api<Machine[]>("/inventory/servers");
      const offStates = new Set(["stopped","stopping","deallocated","off","poweredoff","powered off","terminated"]);
      setInventoryState({total:servers.length,off:servers.filter((item)=>offStates.has(String(item.status||"").toLowerCase())).length,aws:servers.filter((item)=>item.vm_type==="aws").length});
      setRecords(await api<Record<string, unknown>[]>("/decommission-inventory"));
    }
    catch (failure) { setError((failure as Error).message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!selectedName && records.length) setSelectedName(String(records[0].server_name)); }, [records, selectedName]);
  const recordDetails = (record: Record<string, unknown>) => (record.details || {}) as Record<string, unknown>;
  const provider = (record: Record<string, unknown>) => String(record.provider || recordDetails(record).vm_type || "unknown").toLowerCase();
  const recordOs = (record: Record<string, unknown>) => {
    const detail = recordDetails(record);
    const raw = `${record.os_type || detail.os_type || ""} ${record.os_version || detail.os_version || ""}`.toLowerCase();
    return raw.includes("windows") ? "windows" : raw.includes("linux") ? "linux" : /unix|aix|solaris|hp-ux/.test(raw) ? "unix" : "unknown";
  };
  const recordTags = (record: Record<string, unknown>) => {
    const tags = record.tags || recordDetails(record).tags || [];
    return Array.isArray(tags) ? tags.join(" ").toLowerCase() : String(tags).toLowerCase();
  };
  const inScope = (record: Record<string, unknown>, value=scope) => {
    const source = provider(record); const os = recordOs(record); const tags = recordTags(record);
    const onPrem = ["vmware","onprem","on-prem","physical"].includes(source);
    const vmwareHost = source === "vmware" && /asset[_ -]?type=(host|esxi)|esxi host/.test(tags);
    const hardware = source === "physical" || /asset[_ -]?type=hardware|vendor=/.test(tags);
    const vendor = /cisco|ucs/.test(tags) ? "cisco" : /dell/.test(tags) ? "dell" : /hpe|hewlett|vendor=hp\b/.test(tags) ? "hpe" : "other";
    const rules: Record<string,boolean> = {all:true,cloud:["aws","azure"].includes(source),aws:source==="aws","aws:windows":source==="aws"&&os==="windows","aws:linux":source==="aws"&&os==="linux","aws:unix":source==="aws"&&os==="unix",azure:source==="azure","azure:windows":source==="azure"&&os==="windows","azure:linux":source==="azure"&&os==="linux","azure:unix":source==="azure"&&os==="unix",onprem:onPrem,vmware:source==="vmware","vmware:hosts":vmwareHost,"vmware:vms":source==="vmware"&&!vmwareHost,"vmware:vms:windows":source==="vmware"&&!vmwareHost&&os==="windows","vmware:vms:linux":source==="vmware"&&!vmwareHost&&os==="linux","vmware:vms:unix":source==="vmware"&&!vmwareHost&&os==="unix",physical:["physical","onprem","on-prem"].includes(source),"physical:windows":["physical","onprem","on-prem"].includes(source)&&os==="windows","physical:linux":["physical","onprem","on-prem"].includes(source)&&os==="linux","physical:unix":["physical","onprem","on-prem"].includes(source)&&os==="unix",hardware,"hardware:cisco":hardware&&vendor==="cisco","hardware:dell":hardware&&vendor==="dell","hardware:hpe":hardware&&vendor==="hpe","hardware:other":hardware&&vendor==="other"};
    return Boolean(rules[value]);
  };
  const filtered = records.filter((record) => inScope(record) && (!query.trim() || JSON.stringify(record).toLowerCase().includes(query.trim().toLowerCase())));
  const selected = filtered.find((record) => String(record.server_name) === selectedName) || filtered[0];
  const details = (selected?.details || {}) as Record<string, unknown>;
  const lifecycleTree: InventoryNode[] = [
    {id:"all",label:"All lifecycle records",icon:<Database/>},
    {id:"cloud",label:"Cloud",icon:<Cloud/>,children:[
      {id:"aws",label:"Amazon Web Services",icon:<FaAws/>,children:[{id:"aws:windows",label:"Windows",icon:<FaWindows/>},{id:"aws:linux",label:"Linux",icon:<SiLinux/>},{id:"aws:unix",label:"Unix",icon:<Terminal/>}]},
      {id:"azure",label:"Microsoft Azure",icon:<TbBrandAzure/>,children:[{id:"azure:windows",label:"Windows",icon:<FaWindows/>},{id:"azure:linux",label:"Linux",icon:<SiLinux/>},{id:"azure:unix",label:"Unix",icon:<Terminal/>}]},
    ]},
    {id:"onprem",label:"On-premises",icon:<Server/>,children:[
      {id:"vmware",label:"VMware",icon:<SiVmware/>,children:[{id:"vmware:hosts",label:"ESXi hosts",icon:<SiVmware/>},{id:"vmware:vms",label:"Virtual machines",icon:<Boxes/>,children:[{id:"vmware:vms:windows",label:"Windows",icon:<FaWindows/>},{id:"vmware:vms:linux",label:"Linux",icon:<SiLinux/>},{id:"vmware:vms:unix",label:"Unix",icon:<Terminal/>}]}]},
      {id:"physical",label:"Physical servers",icon:<ServerCog/>,children:[{id:"physical:windows",label:"Windows",icon:<FaWindows/>},{id:"physical:linux",label:"Linux",icon:<SiLinux/>},{id:"physical:unix",label:"Unix / AIX / Solaris",icon:<Terminal/>}]},
      {id:"hardware",label:"Hardware platforms",icon:<Cpu/>,children:[{id:"hardware:cisco",label:"Cisco UCS",icon:<SiCisco/>},{id:"hardware:dell",label:"Dell",icon:<SiDell/>},{id:"hardware:hpe",label:"HPE / HP",icon:<GrHpe/>},{id:"hardware:other",label:"Other hardware",icon:<Cpu/>}]},
    ]},
  ];
  const findScopeLabel = (nodes: InventoryNode[]): string => { for (const node of nodes) { if(node.id===scope) return node.label; if(node.children){const found=findScopeLabel(node.children);if(found)return found;} } return ""; };
  const renderLifecycleTree = (nodes: InventoryNode[], depth=0): ReactNode => nodes.map((node)=>{const open=expanded.has(node.id);const total=records.filter((record)=>inScope(record,node.id)).length;return <div className="inventory-node" key={node.id}><button data-node={node.id} className={scope===node.id?"selected":""} style={{paddingLeft:`${8+depth*15}px`}} onClick={()=>{setScope(node.id);if(node.children)setExpanded((current)=>{const next=new Set(current);next.has(node.id)?next.delete(node.id):next.add(node.id);return next;});}}>{node.children?<ChevronRight className={open?"expanded":""}/>:<span className="tree-spacer"/>}{node.icon}<span>{node.label}</span><b>{total}</b></button>{node.children&&open&&<div>{renderLifecycleTree(node.children,depth+1)}</div>}</div>;});
  const lifecycleIcon = (record: Record<string, unknown>) => { const os=recordOs(record); if(os==="windows")return <FaWindows/>;if(os==="linux")return <SiLinux/>;if(os==="unix")return <Terminal/>;const source=provider(record);if(source==="aws")return <FaAws/>;if(source==="azure")return <TbBrandAzure/>;if(source==="vmware")return <SiVmware/>;return <Server/>; };
  const emptyMessage = records.length ? "No lifecycle records match the selected view or search." : inventoryState.total===0 ? "No server inventory has been synchronized for this organization yet." : inventoryState.off===0 ? `Inventory is connected with ${inventoryState.total} active asset(s). Decommission Inventory only includes stopped, deallocated, retired or terminated assets.` : `${inventoryState.off} powered-off asset(s) were detected. Synchronize again to create their lifecycle records.`;
  const exportRecords = () => { const url=URL.createObjectURL(new Blob([JSON.stringify(filtered,null,2)],{type:"application/json"})); const link=document.createElement("a"); link.href=url; link.download="decommission-inventory.json"; link.click(); URL.revokeObjectURL(url); };
  return <section className="asset-workspace decommission-workspace">
    <div className="asset-toolbar"><div><div className="asset-product-mark"><Archive/></div><div><h2>Decommission assets</h2><p>{records.length} lifecycle records · {inventoryState.total} synchronized assets</p></div></div><div className="asset-toolbar-actions"><label><Search/><input value={query} onChange={(event)=>setQuery(event.target.value)} placeholder="Search server, ticket, owner…"/></label><button title="Synchronize AWS and lifecycle inventory" onClick={()=>load(true)} disabled={loading}><RefreshCw className={loading?"spin":""}/></button><button title="Export current view" onClick={exportRecords} disabled={!filtered.length}><Download/></button></div></div>
    {error && <div className="connector-error"><AlertTriangle/><div><strong>Decommission inventory unavailable</strong><p>{error}</p></div></div>}
    {!error && <div className="asset-columns"><aside className="asset-tree"><div className="tree-heading"><span>LIFECYCLE EXPLORER</span><MoreHorizontal/></div><div className="tree-group infrastructure-tree">{renderLifecycleTree(lifecycleTree)}</div></aside>
      <section className="asset-list"><div className="list-heading"><div><strong>{findScopeLabel(lifecycleTree)}</strong><span>{filtered.length} records</span></div><MoreHorizontal/></div><div className="asset-scroll">{loading?<div className="asset-empty">Synchronizing lifecycle records…</div>:filtered.map((record)=><button className={selected?.server_name===record.server_name?"selected":""} onClick={()=>setSelectedName(String(record.server_name))} key={String(record.server_name)}><span className={`asset-os ${recordOs(record)}`}>{lifecycleIcon(record)}</span><div><strong>{String(record.server_name)}</strong><small>{String(record.ticket_reference||record.resource_id||"No ticket")}</small></div><span className={`asset-state ${String(record.lifecycle_state)}`}>{String(record.lifecycle_state).replaceAll("_"," ")}</span></button>)}{!loading&&!filtered.length&&<div className="asset-empty decommission-empty"><Archive/><strong>{records.length?"Nothing matches this view":"No decommission candidates"}</strong><span>{emptyMessage}</span>{!records.length&&<a href="/app/operations/aws">Open AWS operations</a>}</div>}</div></section>
      <section className="asset-detail">{selected?<><header className="asset-detail-header"><div className={`asset-hero-icon ${recordOs(selected)}`}>{lifecycleIcon(selected)}</div><div><span>{String(selected.provider).toUpperCase()} LIFECYCLE RECORD</span><h2>{String(selected.server_name)}</h2><p>{String(details.application||"Unassigned application")} · {String(details.environment||"Unknown environment")}</p></div><span className={`status ${String(selected.power_state)}`}>{String(selected.power_state)}</span></header><nav className="detail-tabs"><span className="active">Decommission details</span></nav><div className="detail-layout"><section className="detail-properties"><h3>Lifecycle record</h3>{[["Lifecycle stage",selected.lifecycle_state],["Power state",selected.power_state],["Decommission ticket",selected.ticket_reference||"—"],["Owner",selected.owner||"Unknown"],["Requested by",selected.requested_by||"—"],["Reason",selected.reason||"—"],["Scream-test started",selected.scream_test_started_at||"—"],["Scream-test ends",selected.scream_test_ends_at||"—"],["Decommissioned at",selected.decommissioned_at||"—"],["Provider",selected.provider],["Resource ID",selected.resource_id||"—"],["Last known IP",selected.ip_address||"—"],["Server team",details.server_team||"—"],["Region",details.region||"—"],["Operating system",details.os_type||"—"],["Record source",selected.source],["Last updated",selected.updated_at]].map(([label,value])=><div key={String(label)}><span>{String(label)}</span><strong>{String(value)}</strong></div>)}</section></div></>:<div className="asset-empty">Select a lifecycle record to inspect its details.</div>}</section>
    </div>}
  </section>;
}

function Inventory({
  servers,
  query,
  setQuery,
}: {
  servers: Machine[];
  query: string;
  setQuery: (x: string) => void;
}) {
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState("");
  const [scope, setScope] = useState("all");
  const [expanded, setExpanded] = useState<Set<string>>(
    new Set(["cloud", "aws", "azure", "onprem", "vmware", "vmware:vms", "physical", "hardware"]),
  );
  const [selectedName, setSelectedName] = useState(
    servers[0]?.server_name || "",
  );
  const [tab, setTab] = useState("Details");
  const normalized = query.trim().toLowerCase();
  const poweredOffStates = new Set(["stopped", "deallocated", "off", "poweredoff", "powered off"]);
  const lifecycleMatch = (server: Machine) => {
    const status = String(server.status || "").toLowerCase();
    return server.enabled !== false && status !== "terminated" && !poweredOffStates.has(status);
  };
  const inScope = (server: Machine, requested = scope) => {
    const provider = (server.vm_type || "unknown").toLowerCase();
    const rawOs = `${server.os_type || ""} ${server.os_version || ""}`.toLowerCase();
    const os = rawOs.includes("windows") ? "windows" : rawOs.includes("linux") ? "linux" : /unix|aix|solaris|hp-ux/.test(rawOs) ? "unix" : "unknown";
    const tags = (server.tags || []).join(" ").toLowerCase();
    const onPrem = ["vmware", "onprem", "on-prem", "physical"].includes(provider);
    const vmwareHost = provider === "vmware" && /asset[_ -]?type=(host|esxi)|esxi host/.test(tags);
    const hardware = provider === "physical" || /asset[_ -]?type=hardware|vendor=/.test(tags);
    const vendor = /cisco|ucs/.test(tags) ? "cisco" : /dell/.test(tags) ? "dell" : /hpe|hewlett|vendor=hp\b/.test(tags) ? "hpe" : "other";
    const rules: Record<string, boolean> = {
      all: true,
      cloud: ["aws", "azure"].includes(provider),
      aws: provider === "aws",
      "aws:windows": provider === "aws" && os === "windows",
      "aws:linux": provider === "aws" && os === "linux",
      "aws:unix": provider === "aws" && os === "unix",
      azure: provider === "azure",
      "azure:windows": provider === "azure" && os === "windows",
      "azure:linux": provider === "azure" && os === "linux",
      "azure:unix": provider === "azure" && os === "unix",
      onprem: onPrem,
      vmware: provider === "vmware",
      "vmware:hosts": vmwareHost,
      "vmware:vms": provider === "vmware" && !vmwareHost,
      "vmware:vms:windows": provider === "vmware" && !vmwareHost && os === "windows",
      "vmware:vms:linux": provider === "vmware" && !vmwareHost && os === "linux",
      "vmware:vms:unix": provider === "vmware" && !vmwareHost && os === "unix",
      physical: ["physical", "onprem", "on-prem"].includes(provider),
      "physical:windows": ["physical", "onprem", "on-prem"].includes(provider) && os === "windows",
      "physical:linux": ["physical", "onprem", "on-prem"].includes(provider) && os === "linux",
      "physical:unix": ["physical", "onprem", "on-prem"].includes(provider) && os === "unix",
      hardware,
      "hardware:cisco": hardware && vendor === "cisco",
      "hardware:dell": hardware && vendor === "dell",
      "hardware:hpe": hardware && vendor === "hpe",
      "hardware:other": hardware && vendor === "other",
    };
    return Boolean(rules[requested]);
  };
  const filtered = servers.filter(
    (server) =>
      lifecycleMatch(server) &&
      inScope(server) &&
      (!normalized ||
        JSON.stringify(server).toLowerCase().includes(normalized)),
  );
  const exportInventory = (format: "csv" | "json" | "excel") => {
    if (!filtered.length) return;
    const rows = filtered.map((server) => ({
      name: server.server_name,
      provider: server.vm_type,
      environment: server.environment,
      status: server.status,
      operating_system: [server.os_type, server.os_version].filter(Boolean).join(" · "),
      private_ip: server.private_ip_address || server.ip_address,
      public_ip: server.public_ip_address,
      private_dns: server.private_dns_name,
      public_dns: server.public_dns_name,
      aws_instance_id: server.aws_instance_id,
      aws_region: server.aws_region,
      application: server.application,
      application_team: server.application_team,
      server_team: server.server_team,
      monitoring: server.monitoring_service,
      services: (server.important_services || []).join(", "),
      tags: (server.tags || []).join(", "),
    }));
    const columns = Object.keys(rows[0]);
    const escapeHtml = (value: unknown) => String(value ?? "").replace(/[&<>]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[character] || character);
    const escapeCsv = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    let body: string;
    let type: string;
    let extension: string;
    if (format === "json") {
      body = JSON.stringify(rows, null, 2);
      type = "application/json;charset=utf-8";
      extension = "json";
    } else if (format === "excel") {
      body = `<html><head><meta charset="utf-8"></head><body><table><thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row[column as keyof typeof row])}</td>`).join("")}</tr>`).join("")}</tbody></table></body></html>`;
      type = "application/vnd.ms-excel;charset=utf-8";
      extension = "xls";
    } else {
      body = [columns.map(escapeCsv).join(","), ...rows.map((row) => columns.map((column) => escapeCsv(row[column as keyof typeof row])).join(","))].join("\n");
      type = "text/csv;charset=utf-8";
      extension = "csv";
    }
    const url = URL.createObjectURL(new Blob([body], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `opsagent-inventory-${scope.replaceAll(":", "-")}.${extension}`;
    link.click();
    URL.revokeObjectURL(url);
  };
  const selected =
    filtered.find((server) => server.server_name === selectedName) ||
    filtered[0];
  useEffect(() => {
    if (
      filtered.length &&
      !filtered.some((x) => x.server_name === selectedName)
    )
      setSelectedName(filtered[0].server_name);
  }, [scope, query, servers]);
  const inventoryTree: InventoryNode[] = [
    { id: "all", label: "All managed assets", icon: <Database /> },
    { id: "cloud", label: "Cloud", icon: <Cloud />, children: [
      { id: "aws", label: "Amazon Web Services", icon: <FaAws />, children: [
        { id: "aws:windows", label: "Windows", icon: <FaWindows /> },
        { id: "aws:linux", label: "Linux", icon: <SiLinux /> },
        { id: "aws:unix", label: "Unix", icon: <Terminal /> },
      ]},
      { id: "azure", label: "Microsoft Azure", icon: <TbBrandAzure />, children: [
        { id: "azure:windows", label: "Windows", icon: <FaWindows /> },
        { id: "azure:linux", label: "Linux", icon: <SiLinux /> },
        { id: "azure:unix", label: "Unix", icon: <Terminal /> },
      ]},
    ]},
    { id: "onprem", label: "On-premises", icon: <Server />, children: [
      { id: "vmware", label: "VMware", icon: <SiVmware />, children: [
        { id: "vmware:hosts", label: "ESXi hosts", icon: <SiVmware /> },
        { id: "vmware:vms", label: "Virtual machines", icon: <Boxes />, children: [
          { id: "vmware:vms:windows", label: "Windows", icon: <FaWindows /> },
          { id: "vmware:vms:linux", label: "Linux", icon: <SiLinux /> },
          { id: "vmware:vms:unix", label: "Unix", icon: <Terminal /> },
        ]},
      ]},
      { id: "physical", label: "Physical servers", icon: <Server />, children: [
        { id: "physical:windows", label: "Windows", icon: <FaWindows /> },
        { id: "physical:linux", label: "Linux", icon: <SiLinux /> },
        { id: "physical:unix", label: "Unix / AIX / Solaris", icon: <Terminal /> },
      ]},
      { id: "hardware", label: "Hardware platforms", icon: <Cpu />, children: [
        { id: "hardware:cisco", label: "Cisco UCS", icon: <SiCisco /> },
        { id: "hardware:dell", label: "Dell", icon: <SiDell /> },
        { id: "hardware:hpe", label: "HPE / HP", icon: <GrHpe /> },
        { id: "hardware:other", label: "Other hardware", icon: <Cpu /> },
      ]},
    ]},
  ];
  const findLabel = (nodes: InventoryNode[]): string => {
    for (const node of nodes) {
      if (node.id === scope) return node.label;
      if (node.children) { const label = findLabel(node.children); if (label) return label; }
    }
    return "";
  };
  const renderTree = (nodes: InventoryNode[], depth = 0): ReactNode => nodes.map((node) => {
    const open = expanded.has(node.id);
    const total = servers.filter((server) => lifecycleMatch(server) && inScope(server, node.id)).length;
    return <div className="inventory-node" key={node.id}>
      <button data-node={node.id} className={scope === node.id ? "selected" : ""} style={{ paddingLeft: `${8 + depth * 15}px` }} onClick={() => {
        setScope(node.id);
        if (node.children) setExpanded((current) => { const next = new Set(current); next.has(node.id) ? next.delete(node.id) : next.add(node.id); return next; });
      }}>
        {node.children ? <ChevronRight className={open ? "expanded" : ""} /> : <span className="tree-spacer" />}
        {node.icon}<span>{node.label}</span><b>{total}</b>
      </button>
      {node.children && open && <div>{renderTree(node.children, depth + 1)}</div>}
    </div>;
  });
  const detailRows: [string, string][] = selected
    ? [
        ["Asset name", selected.server_name],
        ["Platform", selected.vm_type || "Unknown"],
        ["Environment", selected.environment || "Unassigned"],
        [
          "Operating system",
          [selected.os_type, selected.os_version].filter(Boolean).join(" · ") ||
            "Unknown",
        ],
        [
          "Private IP",
          selected.private_ip_address || selected.ip_address || "—",
        ],
        ["Public IP", selected.public_ip_address || "—"],
        ["Private DNS", selected.private_dns_name || "—"],
        ["Public DNS", selected.public_dns_name || "—"],
        ["OS hostname", selected.host_name || "Unavailable — requires SSM"],
        ["AWS instance ID", selected.aws_instance_id || "—"],
        ["AWS region", selected.aws_region || "—"],
        ["Instance type", selected.instance_type || "—"],
        ["Architecture", selected.architecture || "—"],
        ["Availability zone", selected.availability_zone || "—"],
        ["VPC", selected.vpc_id || "—"],
        ["Subnet", selected.subnet_id || "—"],
        ["EBS storage", selected.storage_volumes?.length
          ? `${selected.storage_volumes.length} volume${selected.storage_volumes.length === 1 ? "" : "s"} · ${selected.storage_volumes.reduce((total, volume) => total + (volume.size_gib || 0), 0)} GiB`
          : "No EBS details returned"],
        ["EBS volumes", selected.storage_volumes?.length
          ? selected.storage_volumes.map((volume) => [volume.device, volume.volume_id, volume.size_gib ? `${volume.size_gib} GiB` : "", volume.volume_type, volume.encrypted === true ? "encrypted" : volume.encrypted === false ? "unencrypted" : ""].filter(Boolean).join(" · ")).join(" | ")
          : "—"],
        ["Gateway", selected.gateway_ip || "—"],
        ["Management port", String(selected.remote_port || "—")],
        ["Monitoring", selected.monitoring_service || "Not assigned"],
      ]
    : [];
  return (
    <section className="asset-workspace">
      <div className="asset-toolbar">
        <div>
          <div className="asset-product-mark">
            <img src="/opsagent-mark.svg" alt="OpsAgent" />
          </div>
          <div>
            <h2>Infrastructure assets</h2>
            <p>
              {servers.length} resources synchronized across your organization
            </p>
          </div>
        </div>
        <div className="asset-toolbar-actions">
          <label>
            <Search />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search assets, IP, application…"
            />
          </label>
          <button title="Synchronize AWS inventory" disabled={refreshing} onClick={async () => {
            setRefreshing(true);
            setRefreshError("");
            try {
              await api("/connections/aws/sync", { method: "POST" });
              location.reload();
            } catch (error) {
              setRefreshError((error as Error).message);
              setRefreshing(false);
            }
          }}>
            <RefreshCw className={refreshing ? "spin" : ""} />
          </button>
          <label className="inventory-export-control" title="Export current inventory view">
            <Download />
            <select defaultValue="" onChange={(event) => {
              const format = event.target.value as "csv" | "json" | "excel";
              if (format) exportInventory(format);
              event.target.value = "";
            }} disabled={!filtered.length}>
              <option value="" disabled>Export</option>
              <option value="csv">CSV</option>
              <option value="json">JSON</option>
              <option value="excel">Excel</option>
            </select>
          </label>
        </div>
      </div>
      {refreshError && <div className="inventory-sync-error">{refreshError}</div>}
      <div className="asset-columns">
        <aside className="asset-tree">
          <div className="tree-heading">
            <span>RESOURCE EXPLORER</span>
            <MoreHorizontal />
          </div>
          <div className="tree-group infrastructure-tree">{renderTree(inventoryTree)}</div>
        </aside>
        <section className="asset-list">
          <div className="list-heading">
            <div>
              <strong>
                {findLabel(inventoryTree) || "All assets"}
              </strong>
              <span>{filtered.length} objects</span>
            </div>
            <MoreHorizontal />
          </div>
          <div className="asset-scroll">
            {filtered.map((server) => (
              <button
                className={
                  selected?.server_name === server.server_name ? "selected" : ""
                }
                onClick={() => setSelectedName(server.server_name)}
                key={server.server_name}
              >
                <span className={`asset-os ${machineIconKind(server)}`}>
                  {machineIcon(server)}
                </span>
                <div>
                  <strong>{server.server_name}</strong>
                  <small>
                    {server.private_ip_address ||
                      server.ip_address ||
                      "Address unavailable"}
                  </small>
                </div>
                <span className={`asset-state ${server.status?.toLowerCase()}`}>
                  {server.status || "unknown"}
                </span>
              </button>
            ))}
            {!filtered.length && (
              <div className="asset-empty">No assets match this view.</div>
            )}
          </div>
        </section>
        <section className="asset-detail">
          {selected ? (
            <>
              <header className="asset-detail-header">
                <div
                  className={`asset-hero-icon ${machineIconKind(selected)}`}
                >
                  {machineIcon(selected)}
                </div>
                <div>
                  <span>{selected.vm_type?.toUpperCase()} RESOURCE</span>
                  <h2>{selected.server_name}</h2>
                  <p>
                    {selected.application || "Unassigned application"} ·{" "}
                    {selected.environment || "Unknown environment"}
                  </p>
                </div>
                <span className={`status ${selected.status?.toLowerCase()}`}>
                  {selected.status}
                </span>
                <button>
                  <MoreHorizontal />
                </button>
              </header>
              <nav className="detail-tabs">
                {["Details", "Activity"].map((item) => (
                  <button
                    className={tab === item ? "active" : ""}
                    onClick={() => setTab(item)}
                    key={item}
                  >
                    {item}
                  </button>
                ))}
              </nav>
              {tab === "Details" ? (
                <div className="detail-layout">
                  <div className="detail-properties">
                    <h3>Resource properties</h3>
                    {detailRows.map(([label, value]) => (
                      <div key={label}>
                        <span>{label}</span>
                        <strong>{value}</strong>
                      </div>
                    ))}
                  </div>
                  <aside className="asset-context">
                    <section>
                      <h3>Ownership</h3>
                      <div>
                        <span>Application</span>
                        <strong>{selected.application || "Unassigned"}</strong>
                      </div>
                      <div>
                        <span>Application team</span>
                        <strong>
                          {selected.application_team || "Unassigned"}
                        </strong>
                      </div>
                      <div>
                        <span>Server team</span>
                        <strong>{selected.server_team || "Unassigned"}</strong>
                      </div>
                    </section>
                    <section>
                      <h3>Linked services</h3>
                      {selected.important_services?.length ? (
                        selected.important_services.map((service) => (
                          <span className="service-chip" key={service}>
                            {service}
                          </span>
                        ))
                      ) : (
                        <p>No linked services recorded.</p>
                      )}
                    </section>
                    <section>
                      <h3>Tags</h3>
                      {selected.tags?.length ? (
                        selected.tags.map((tag) => (
                          <span className="tag-chip" key={tag}>
                            {tag}
                          </span>
                        ))
                      ) : (
                        <p>No tags assigned.</p>
                      )}
                    </section>
                  </aside>
                </div>
              ) : (
                <div className="asset-activity">
                  <Activity />
                  <h3>Inventory activity</h3>
                  <p>
                    This resource is enabled and available to OpsAgent.
                    Discovery and operation events will appear here as
                    organization-scoped audit data is collected.
                  </p>
                  <div>
                    <span>Current state</span>
                    <strong>{selected.status}</strong>
                  </div>
                  <div>
                    <span>Inventory source</span>
                    <strong>{selected.vm_type || "PostgreSQL"}</strong>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="asset-empty">
              Select an asset to inspect its details.
            </div>
          )}
        </section>
      </div>
    </section>
  );
}

function SimpleTable({ rows, title = "Records" }: { rows: Record<string, unknown>[] | Health[]; title?: string }) {
  const normalized = rows as Record<string, unknown>[];
  const columns = normalized.length ? Object.keys(normalized[0]) : [];
  const [search, setSearch] = useState("");
  const [filterColumn, setFilterColumn] = useState("all");
  const [filterValue, setFilterValue] = useState("");
  const [sort, setSort] = useState<{ column: string; direction: "asc" | "desc" }>({ column: "", direction: "asc" });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  useEffect(() => setPage(1), [search, filterColumn, filterValue, pageSize]);
  const text = (value: unknown) => String(value ?? "");
  const filtered = normalized.filter((row) => {
    const searchMatch = !search || columns.some((column) => text(row[column]).toLowerCase().includes(search.toLowerCase()));
    const filterMatch = !filterValue || (filterColumn === "all"
      ? columns.some((column) => text(row[column]).toLowerCase().includes(filterValue.toLowerCase()))
      : text(row[filterColumn]).toLowerCase().includes(filterValue.toLowerCase()));
    return searchMatch && filterMatch;
  });
  const sorted = [...filtered].sort((a, b) => {
    if (!sort.column) return 0;
    return text(a[sort.column]).localeCompare(text(b[sort.column]), undefined, { numeric: true }) * (sort.direction === "asc" ? 1 : -1);
  });
  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const currentPage = Math.min(page, pages);
  const visible = sorted.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const toggleSort = (column: string) => setSort((old) => ({ column, direction: old.column === column && old.direction === "asc" ? "desc" : "asc" }));
  const exportCsv = () => {
    const escape = (value: unknown) => `"${text(value).replaceAll('"', '""')}"`;
    const csv = [columns.map(escape).join(","), ...sorted.map((row) => columns.map((column) => escape(row[column])).join(","))].join("\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    link.download = `${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  };
  return (
    <section className="data-grid">
      <header className="data-grid-header"><div><h3>{title}</h3><span>{filtered.length} of {normalized.length} records</span></div><div className="data-grid-actions"><label className="grid-search"><Search size={15}/><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search all records" /></label><button className="secondary" onClick={exportCsv} disabled={!filtered.length}><Download size={15}/> Export CSV</button></div></header>
      <div className="data-grid-filters"><Filter size={14}/><select value={filterColumn} onChange={(e) => setFilterColumn(e.target.value)}><option value="all">All columns</option>{columns.map((column) => <option value={column} key={column}>{column}</option>)}</select><input value={filterValue} onChange={(e) => setFilterValue(e.target.value)} placeholder="Filter value…" />{(search || filterValue) && <button onClick={() => { setSearch(""); setFilterValue(""); }}>Clear filters</button>}</div>
      {visible.length ? <div className="table-scroll"><table>
        <thead>
          <tr>
            {columns.map((x) => (
              <th key={x}><button className={sort.column === x ? "sorted" : ""} onClick={() => toggleSort(x)}>{x}<span>{sort.column === x ? (sort.direction === "asc" ? "↑" : "↓") : "↕"}</span></button></th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visible.map((row, i) => (
            <tr key={i}>
              {columns.map((x) => (
                <td key={x}>{String(row[x] ?? "—")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table></div> : <div className="data-grid-empty"><Search/><strong>No matching records</strong><span>Change or clear the current filters.</span></div>}
      <footer className="data-grid-footer"><label>Rows per page <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}><option>10</option><option>25</option><option>50</option><option>100</option></select></label><span>{sorted.length ? `${(currentPage - 1) * pageSize + 1}–${Math.min(currentPage * pageSize, sorted.length)} of ${sorted.length}` : "0 records"}</span><div><button onClick={() => setPage(1)} disabled={currentPage === 1}>«</button><button onClick={() => setPage((x) => Math.max(1, x - 1))} disabled={currentPage === 1}>‹</button><b>Page {currentPage} of {pages}</b><button onClick={() => setPage((x) => Math.min(pages, x + 1))} disabled={currentPage === pages}>›</button><button onClick={() => setPage(pages)} disabled={currentPage === pages}>»</button></div></footer>
    </section>
  );
}

function RemoteWorkspace({
  endpoint,
  title,
}: {
  endpoint: string;
  title: string;
}) {
  const [data, setData] = useState<Record<string, unknown> | unknown[] | null>(
    null,
  );
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const load = () => api<Record<string, unknown> | unknown[]>(endpoint)
      .then((next) => { if (active) { setData(next); setError(""); } })
      .catch((e) => { if (active) setError(e.message); });
    load();
    const refresh = window.setInterval(load, 5000);
    return () => { active = false; window.clearInterval(refresh); };
  }, [endpoint]);
  if (error) return <p className="error">{error}</p>;
  if (!data) return <div className="skeleton">Loading live data…</div>;
  const summary =
    !Array.isArray(data) &&
    (data.summary as Record<string, unknown> | undefined);
  const rows = (Array.isArray(data) ? data : data.events || []) as Record<
    string,
    unknown
  >[];
  return (
    <>
      <section className="section-heading">
        <div>
          <h2>{title}</h2>
          <p>Live operational data from PostgreSQL</p>
        </div>
      </section>
      {summary && (
        <section className="metrics compact">
          {Object.entries(summary)
            .slice(0, 6)
            .map(([k, v]) => (
              <article key={k}>
                <span>{k.replaceAll("_", " ")}</span>
                <strong>{String(v)}</strong>
              </article>
            ))}
        </section>
      )}
      <SimpleTable rows={rows} title={title} />
    </>
  );
}

function AgentHealthWorkspace({health}:{health:Health[]}) {
  const healthy = health.filter((item)=>item.Status.toLowerCase()==="healthy");
  const attention = health.filter((item)=>item.Status.toLowerCase()!=="healthy");
  const readiness = health.length ? Math.round(healthy.length/health.length*100) : 0;
  return <section className="product-page agent-health-page">
    <div className="page-lead"><div><span className="badge">CONTROL PLANE HEALTH</span><h2>Agent and connector health</h2><p>Live runtime state for every OpsAgent service, connector and background worker.</p></div><div className="health-readiness"><strong>{readiness}%</strong><span>Operational readiness</span></div></div>
    <div className="analytics-kpis"><article><span>Total components</span><strong>{health.length}</strong><small>Registered control-plane services</small></article><article><span>Healthy</span><strong>{healthy.length}</strong><small>Operating normally</small></article><article><span>Needs attention</span><strong>{attention.length}</strong><small>Disabled, unknown or failed</small></article><article><span>Last refresh</span><strong className="small-value">Live</strong><small>From component heartbeat records</small></article></div>
    <div className="health-report-grid"><article className="analytics-health-card healthy"><header><span><CheckCircle2/> Healthy services</span><strong>{healthy.length}</strong></header><div>{healthy.map((item)=><section key={item.Component}><i/><span><b>{item.Component}</b><small>{item.Details||"Operating normally"} · {item["Last heartbeat"]}</small></span><em>Healthy</em></section>)}{!healthy.length&&<p>No healthy services reported.</p>}</div></article><article className="analytics-health-card attention"><header><span><AlertTriangle/> Needs attention</span><strong>{attention.length}</strong></header><div>{attention.map((item)=><section key={item.Component}><i/><span><b>{item.Component}</b><small>{item.Details||"Status requires review"} · {item["Last heartbeat"]}</small></span><em>{item.Status}</em></section>)}{!attention.length&&<p>All services are healthy.</p>}</div></article></div>
  </section>;
}

type AlertPayload = {
  summary: Record<string, unknown>;
  events: Record<string, unknown>[];
};

function AlertOperations({ channel, health }: { channel: "slack" | "gmail"; health: Health[] }) {
  const [data, setData] = useState<AlertPayload | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const isSlack = channel === "slack";
  const componentName = isSlack ? "Slack" : "Inbound Email";
  const component = health.find((item) => item.Component === componentName);
  const load = async (quiet = false) => {
    if (!quiet) setRefreshing(true);
    try {
      setData(await api<AlertPayload>(`/alerts/${channel}?hours=24`));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load connector events");
    } finally {
      setRefreshing(false);
    }
  };
  useEffect(() => {
    load();
    const timer = window.setInterval(() => load(true), 30000);
    return () => window.clearInterval(timer);
  }, [channel]);

  const metrics = isSlack
    ? [["Received", "received"], ["Acknowledged", "acknowledged"], ["Completed", "processed"], ["Outstanding", "outstanding"], ["Acknowledgement rate", "acknowledgement_rate"], ["Average response", "average_ack_seconds"]]
    : [["Received", "received"], ["Acknowledged", "acknowledged"], ["Processed", "processed"], ["Failed", "failed"], ["Acknowledgement rate", "acknowledgement_rate"], ["Average response", "average_ack_seconds"]];
  const columns = isSlack
    ? [["Received", "received_at"], ["Request / alert", "alert"], ["Target", "target"], ["Status", "status"], ["Acknowledged in", "acknowledgement_time"], ["Completed in", "processing_time"]]
    : [["Received", "Received"], ["Sender", "Sender"], ["Subject", "Subject"], ["Request ID", "Request ID"], ["Status", "Status"], ["Acknowledged in", "Acknowledgement time"]];
  const formatMetric = (key: string, value: unknown) => {
    if (value === null || value === undefined || value === "") return "—";
    if (key === "acknowledgement_rate") return `${value}%`;
    if (key === "average_ack_seconds") {
      const seconds = Number(value);
      return Number.isFinite(seconds) ? `${seconds < 10 ? seconds.toFixed(2) : seconds.toFixed(1)}s` : `${value}s`;
    }
    return String(value);
  };
  const connectorStatus = (component?.Status || "unknown").toLowerCase();
  const connectorHealthy = ["healthy", "running", "connected"].includes(connectorStatus);

  return (
    <div className="alert-operations">
      <section className="alert-page-heading">
        <div className={`channel-mark ${channel}`}>{isSlack ? <FaSlack /> : <SiGmail />}</div>
        <div><span>MONITORING INTEGRATION</span><h2>{isSlack ? "Slack alert operations" : "Gmail request operations"}</h2><p>Requests, acknowledgements and completed actions from the last 24 hours.</p></div>
        <div className="connector-actions">
          {data && <span className="connector-state data-connected"><i />Data connected</span>}
          <span className={`connector-state ${connectorStatus}`} title={component?.Details || "Connector runtime status"}><i />{connectorHealthy ? "Connector healthy" : component?.Status || "Status unknown"}</span>
          <button className="secondary" onClick={() => load()} disabled={refreshing}><RefreshCw size={15} className={refreshing ? "spin" : ""} /> Refresh</button>
        </div>
      </section>
      {error && <section className="connector-error"><AlertTriangle /><div><strong>Connector data is unavailable</strong><p>{error}</p></div><button onClick={() => load()}>Try again</button></section>}
      {data && <>
        <section className="alert-metrics">{metrics.map(([label, key], index) => <article key={key} className={key === "failed" && Number(data.summary[key]) > 0 ? "metric-alert" : ""}><i>{String(index + 1).padStart(2, "0")}</i><span>{label}</span><strong>{formatMetric(key, data.summary[key])}</strong><small>{key === "average_ack_seconds" ? "Average for this period" : "Last 24 hours"}</small></article>)}</section>
        <section className="alert-event-panel"><div className="panel-title"><div><span>ACTIVITY</span><h3>Operational timeline</h3><p>Request → acknowledgement → approval → verified result</p></div><span><i /> Live · refreshes every 30 seconds</span></div>
          {data.events.length ? <SimpleTable title={`${isSlack ? "Slack" : "Gmail"} operational events`} rows={data.events.map((row) => Object.fromEntries(columns.map(([label, key]) => [label, row[key] ?? "—"])))} /> : <div className="empty-events"><CheckCircle2 /><strong>No events in the last 24 hours</strong><span>The connector is ready; new alerts and requests will appear here automatically.</span></div>}
        </section>
      </>}
    </div>
  );
}

type HardwareDashboard = { summary:{assets:number;chassis:number;blades:number;healthy_blades:number;active_alerts:number;coverage:number;vendors:Record<string,number>;types:Record<string,number>}; assets:Record<string,unknown>[]; alerts:{asset:string;component:string;type:string;severity:string;status:string;detected_at:string;error:string;likely_cause:string;mitigation:string[];ticket_status:string}[]; tickets:{request_id:string;status:string;asset:string;component:string;summary:string}[]; last_scan:string|null; connector:{configured:boolean;status:string}; report:{schedule:string;recipients:string;last_status:string;next_report:string} };

function HardwareInventoryWorkspace({onNavigate}:{onNavigate?:(page:string)=>void}) {
  const [data,setData]=useState<HardwareDashboard|null>(null); const [scope,setScope]=useState("All hardware"); const [query,setQuery]=useState(""); const [selected,setSelected]=useState<Record<string,unknown>|null>(null);
  useEffect(()=>{api<HardwareDashboard>("/hardware/dashboard").then(setData);},[]);
  if(!data)return <div className="skeleton">Loading hardware inventory…</div>;
  const rows=data.assets.filter(item=>(scope==="All hardware"||String(item.vendor||item.asset_type)===scope)&&JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  const groups=[{label:"All hardware",count:data.summary.assets,icon:ServerCog},...Object.entries(data.summary.vendors).map(([label,count])=>({label,count,icon:label==="Dell"?SiDell:label==="HPE"?GrHpe:SiCisco})),...Object.entries(data.summary.types).map(([label,count])=>({label,count,icon:label==="Chassis"?Boxes:label==="Blade"?Server:Database}))];
  return <section className="hardware-inventory-page"><div className="hardware-inventory-toolbar"><div><ServerCog/><span><strong>Hardware inventory</strong><small>{data.summary.assets} assets synchronized across your organization</small></span></div><label><Search/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Search serial, chassis, blade, IP…"/></label><button onClick={()=>onNavigate?.("Connections")}><Plug/> Add source</button></div><div className="hardware-inventory-columns"><aside className="hardware-tree"><header>HARDWARE EXPLORER</header>{groups.map(({label,count,icon:Icon})=><button key={label} className={scope===label?"selected":""} onClick={()=>{setScope(label);setSelected(null);}}><Icon/><span>{label}</span><b>{count}</b></button>)}</aside><section className="hardware-list"><header><div><strong>{scope}</strong><span>{rows.length} assets</span></div></header>{rows.length?rows.map(item=><button key={String(item.id||item.serial_number||item.name)} className={selected===item?"selected":""} onClick={()=>setSelected(item)}><ServerCog/><span><strong>{String(item.name||item.hostname||"Hardware asset")}</strong><small>{String(item.vendor||"Unknown vendor")} · {String(item.model||item.asset_type||"Unknown type")}</small></span><b>{String(item.status||"Unknown")}</b></button>):<div className="hardware-list-empty"><ServerCog/><strong>No hardware assets</strong><span>Connect Cisco, Dell or HPE management to populate inventory.</span></div>}</section><section className="hardware-detail">{selected?<><header><ServerCog/><div><span>HARDWARE ASSET</span><h2>{String(selected.name||selected.hostname)}</h2><p>{String(selected.vendor||"Unknown")} · {String(selected.model||selected.asset_type||"Unknown")}</p></div></header><div>{Object.entries(selected).filter(([key])=>!key.startsWith("_")).map(([key,value])=><section key={key}><span>{key.replaceAll("_"," ")}</span><strong>{typeof value==="object"?JSON.stringify(value):String(value??"—")}</strong></section>)}</div></>:<div className="hardware-detail-empty"><ServerCog/><strong>Select a hardware asset</strong><span>Review chassis, blade, serial, firmware and component-health details.</span></div>}</section></div></section>;
}

function HardwareMonitoringWorkspace({onNavigate}:{onNavigate?:(page:string)=>void}) {
  const [data,setData]=useState<HardwareDashboard|null>(null); const [busy,setBusy]=useState(""); const [message,setMessage]=useState("");
  const load=()=>api<HardwareDashboard>("/hardware/dashboard").then(setData);
  useEffect(()=>{load();},[]);
  const act=async(path:string,label:string,body?:unknown)=>{setBusy(label);setMessage("");try{await api(path,{method:"POST",body:body?JSON.stringify(body):undefined});await load();setMessage(`${label} completed.`);}catch(error){setMessage((error as Error).message);}finally{setBusy("");}};
  if(!data)return <div className="skeleton">Loading hardware estate…</div>;
  const ask=(alert?:HardwareDashboard["alerts"][number])=>{sessionStorage.setItem("opsagent-chat-draft",alert?`Hardware Agent: explain ${alert.error} on ${alert.asset} ${alert.component} and provide safe mitigation steps.`:"Hardware Agent: summarize today’s chassis and blade health.");onNavigate?.("OpsAgent chat");};
  return <section className="hardware-monitoring product-page"><div className="page-lead"><div><span className="badge">HARDWARE MONITORING AGENT</span><h2>Enterprise hardware health</h2><p>Daily inspection across Cisco, Dell and HPE hardware with component diagnosis, mitigation guidance, reporting and approval-gated ITSM escalation.</p></div><div className="hardware-lead-actions"><button className="secondary-action" onClick={()=>ask()}><Sparkles/> Ask agent</button>{data.connector.configured?<button className="primary-action" disabled={!!busy} onClick={()=>act("/hardware/scan","Hardware scan")}><RefreshCw className={busy==="Hardware scan"?"spin":""}/> Scan now</button>:<button className="primary-action" onClick={()=>onNavigate?.("Connections")}><Plug/> Configure connection</button>}</div></div>
  {message&&<div className="hardware-message">{message}</div>}
  <div className="hardware-kpis five"><article><span>Hardware assets</span><strong>{data.summary.assets}</strong><small>Across all vendors</small></article><article><span>Chassis</span><strong>{data.summary.chassis}</strong><small>Cisco · Dell · HPE</small></article><article><span>Blades healthy</span><strong>{data.summary.healthy_blades}<small> / {data.summary.blades}</small></strong><small>Daily hardware validation</small></article><article><span>Active findings</span><strong className="attention">{data.summary.active_alerts}</strong><small>Require operator review</small></article><article><span>Inspection coverage</span><strong>{data.summary.coverage}%</strong><small>{data.last_scan?`Last scan ${new Date(data.last_scan).toLocaleString()}`:"No scan completed"}</small></article></div>
  <div className="hardware-main-grid"><article className="hardware-panel"><header><div><span>HARDWARE ESTATE</span><h3>Chassis overview</h3></div><b>{data.summary.blades} blades</b></header><div className="hardware-assets">{data.assets.length?data.assets.map((asset)=><section key={String(asset.id)}><ServerCog/><div><strong>{String(asset.name)}</strong><span>{String(asset.vendor)} · {String(asset.model)} · {String(asset.site)}</span><small>{String(asset.management_ip)} · Power {String(asset.power)} · Temperature {String(asset.temperature)}</small></div><b className={String(asset.status).toLowerCase()}>{String(asset.status)}</b><em>{String(asset.healthy_blades)}/{String(asset.blades)} healthy</em></section>):<div className="hardware-empty"><ServerCog/><strong>No hardware connector configured</strong><span>Add a hardware URL, API endpoint or management IP when it is available.</span><button onClick={()=>onNavigate?.("Connections")}>Configure hardware connection</button></div>}</div></article><article className="hardware-panel report-panel"><header><div><span>DAILY REPORT</span><h3>Email delivery</h3></div><Mail/></header><div><strong>{data.report.schedule}</strong><span>{data.report.recipients}</span><small>{data.report.last_status} · {data.report.next_report}</small>{data.connector.configured&&<button disabled={!!busy} onClick={()=>act("/hardware/reports/daily","Daily report")}>Send report now</button>}</div></article></div>
  <article className="hardware-panel findings-panel"><header><div><span>DIAGNOSIS AND MITIGATION</span><h3>Active hardware findings</h3></div><b>{data.alerts.length} open</b></header><div>{data.alerts.length?data.alerts.map((alert,index)=><section key={`${alert.asset}-${alert.component}`}><div className={`hardware-severity ${alert.severity.toLowerCase()}`}><AlertTriangle/><span>{alert.severity}</span></div><div className="finding-copy"><span>{alert.asset} · {alert.component}</span><h4>{alert.error}</h4><p><b>Likely cause:</b> {alert.likely_cause}</p><ol>{alert.mitigation.map(step=><li key={step}>{step}</li>)}</ol></div><div className="finding-actions"><span>{alert.ticket_status}</span><button onClick={()=>ask(alert)}>Ask agent</button><button className="ticket-action" disabled={!!busy||alert.ticket_status==="Pending approval"} onClick={()=>act("/hardware/tickets","Ticket request",{alert_index:index})}>Request ticket approval</button></div></section>):<div className="hardware-empty compact"><CheckCircle2/><strong>No hardware findings</strong><span>Findings will appear after a connector is configured and the first inspection completes.</span></div>}</div></article>
  {data.tickets.length>0&&<article className="hardware-panel ticket-panel"><header><div><span>APPROVAL QUEUE</span><h3>ITSM ticket requests</h3></div></header>{data.tickets.map(ticket=><section key={ticket.request_id}><div><strong>{ticket.request_id}</strong><span>{ticket.asset} · {ticket.component}</span><small>{ticket.summary}</small></div><b>{ticket.status}</b>{ticket.status==="Pending approval"&&<button onClick={()=>act(`/hardware/tickets/${ticket.request_id}/approve`,"Ticket approval")}>Approve and queue</button>}</section>)}</article>}
  </section>;
}

function ProviderWorkspace({ provider }: { provider: string }) {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  useEffect(() => {
    api<Record<string, unknown>[]>(`/operations/${provider}/inventory`).then(
      setRows,
    );
  }, [provider]);
  return (
    <>
      <section className="section-heading">
        <div>
          <h2>{provider.toUpperCase()} estate</h2>
          <p>Discovered and registered provider resources</p>
        </div>
      </section>
      <SimpleTable rows={rows} title={`${provider.toUpperCase()} resources`} />
    </>
  );
}

function Chat() {
  type Session = { session_id: string; title: string; persona: string };
  type Attachment = { name: string; content: string };
  const [sessions, setSessions] = useState<Session[]>([]);
  const [session, setSession] = useState("");
  const [messages, setMessages] = useState<{ role: string; content: string }[]>(
    [],
  );
  const initialDraft = sessionStorage.getItem("opsagent-chat-draft") || "";
  const [text, setText] = useState(() => initialDraft.startsWith("Provision a new AWS EC2") ? "" : initialDraft);
  const [provisionOpen, setProvisionOpen] = useState(() => initialDraft.startsWith("Provision a new AWS EC2"));
  const [vmRequest, setVmRequest] = useState({ name: "", region: "us-east-1", os: "Windows Server 2022", size: "t3.medium", vpc: "Default VPC", subnet: "Auto-select private subnet", security: "default", storage: "80", access: "AWS Systems Manager", keyName: "", monitoring: "CloudWatch enabled", backup: "Daily snapshot", environment: "Development" });
  const [vmPreview, setVmPreview] = useState<Record<string, unknown> | null>(null);
  const [vmConfirmation, setVmConfirmation] = useState("");
  const [vmResult, setVmResult] = useState<Record<string, unknown> | null>(null);
  const [vmError, setVmError] = useState("");
  const [awsOptions, setAwsOptions] = useState<{vpcs:{id:string;name:string;cidr:string}[];subnets:{id:string;name:string;vpc_id:string;zone:string;public:boolean}[];security_groups:{id:string;name:string;vpc_id:string}[];key_pairs:{name:string;id:string}[]} | null>(null);
  const [awsOptionsError, setAwsOptionsError] = useState("");
  const [terminationCodes, setTerminationCodes] = useState<Record<string,string>>({});
  const [terminationBackups, setTerminationBackups] = useState<Record<string,boolean>>({});
  const [terminationResults, setTerminationResults] = useState<Record<string,string>>({});
  const [busy, setBusy] = useState(false);
  const [persona, setPersona] = useState("Senior Infrastructure Architect");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [listening, setListening] = useState<"dictation" | "voice" | "">("");
  const recognition = useRef<Recognition | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const guidedForm = useRef<HTMLFormElement>(null);
  function listen(mode: "dictation" | "voice") {
    if (listening) {
      recognition.current?.stop();
      setListening("");
      return;
    }
    const browser = window as unknown as {
      SpeechRecognition?: new () => Recognition;
      webkitSpeechRecognition?: new () => Recognition;
    };
    const RecognitionEngine =
      browser.SpeechRecognition || browser.webkitSpeechRecognition;
    if (!RecognitionEngine) {
      alert("Speech recognition requires the latest Chrome or Edge browser.");
      return;
    }
    const engine = new RecognitionEngine();
    engine.continuous = mode === "voice";
    engine.interimResults = true;
    engine.lang = navigator.language || "en-US";
    engine.onresult = (event) => {
      let transcript = "";
      for (let i = 0; i < event.results.length; i += 1)
        transcript += event.results[i][0].transcript;
      setText(transcript);
    };
    engine.onend = () => setListening("");
    engine.onerror = () => setListening("");
    recognition.current = engine;
    setListening(mode);
    engine.start();
  }
  async function refresh(preferred?: string) {
    let list = await api<Session[]>("/chat/sessions");
    if (!list.length) {
      const made = await api<{ session_id: string }>("/chat/sessions", {
        method: "POST",
      });
      list = [{ session_id: made.session_id, title: "New chat", persona }];
    }
    setSessions(list);
    setSession(preferred || session || list[0].session_id);
  }
  useEffect(() => {
    sessionStorage.removeItem("opsagent-chat-draft");
    refresh();
  }, []);
  useEffect(() => {
    if (session)
      api<typeof messages>(`/chat/sessions/${session}`).then(setMessages);
  }, [session]);
  useEffect(() => {
    if (!provisionOpen) return;
    api<typeof awsOptions>(`/operations/aws/provision/options?region=${encodeURIComponent(vmRequest.region)}`).then((options) => {
      if (!options) return;
      setAwsOptions(options);
      setAwsOptionsError("");
      const vpc = options.vpcs.find((item) => item.name === "Default VPC") || options.vpcs[0];
      const subnet = options.subnets.find((item) => item.vpc_id === vpc?.id && !item.public) || options.subnets.find((item) => item.vpc_id === vpc?.id);
      const group = options.security_groups.find((item) => item.vpc_id === vpc?.id && item.name === "default") || options.security_groups.find((item) => item.vpc_id === vpc?.id);
      setVmRequest((current) => ({...current, vpc:vpc?.id || current.vpc, subnet:subnet?.id || current.subnet, security:group?.id || current.security}));
    }).catch((error) => { setAwsOptions(null); setAwsOptionsError((error as Error).message); });
  }, [provisionOpen, vmRequest.region]);
  useEffect(() => {
    if (!provisionOpen) return;
    const timer = window.setTimeout(() => guidedForm.current?.scrollIntoView({behavior:"smooth", block:"start"}), 80);
    return () => window.clearTimeout(timer);
  }, [provisionOpen]);
  async function addFiles(files: FileList | null) {
    if (!files) return;
    const added: Attachment[] = [];
    for (const file of Array.from(files).slice(0, 5)) {
      const textTypes = [
        "text/",
        "application/json",
        "application/xml",
        "application/csv",
      ];
      const readable =
        textTypes.some((x) => file.type.startsWith(x)) ||
        /\.(txt|log|md|json|csv|xml|yaml|yml|ps1|py|sh)$/i.test(file.name);
      added.push({
        name: file.name,
        content: readable
          ? (await file.text()).slice(0, 50000)
          : `Binary attachment (${file.type || "unknown type"}, ${file.size} bytes). Analyze using its metadata.`,
      });
    }
    setAttachments((x) => [...x, ...added].slice(0, 5));
  }
  async function send(e: FormEvent) {
    e.preventDefault();
    if ((!text.trim() && !attachments.length) || busy) return;
    recognition.current?.stop();
    const question =
      text || `Please review ${attachments.map((x) => x.name).join(", ")}`;
    const provisioningIntent = /\bprovision(?:ing|ed)?\b|\b(create|build|launch|deploy|new)\b[\s\S]{0,80}\b(ec2|vm|virtual machine|aws server|cloud server|instance)\b|\b(ec2|vm|virtual machine|aws server|cloud server|instance)\b[\s\S]{0,80}\b(create|build|launch|deploy|new)\b/i.test(question);
    if (provisioningIntent) {
      recognition.current?.stop();
      setText("");
      setAttachments([]);
      setMessages((current) => [...current, { role: "user", content: question }]);
      setVmPreview(null); setVmResult(null); setVmConfirmation("");
      setProvisionOpen(true);
      return;
    }
    setText("");
    setMessages((x) => [...x, { role: "user", content: question }]);
    setBusy(true);
    try {
      const reply = await api<{ role: string; content: string }>(
        "/chat/messages",
        {
          method: "POST",
          body: JSON.stringify({
            session_id: session,
            message: question,
            persona,
            attachments,
          }),
        },
      );
      setMessages((x) => [...x, reply]);
      setAttachments([]);
      refresh(session);
    } finally {
      setBusy(false);
    }
  }
  async function sendVmRequest(e: FormEvent) {
    e.preventDefault();
    if (!vmRequest.name.trim() || busy || !session) return;
    const payload = { name: vmRequest.name, region: vmRequest.region, os: vmRequest.os, instance_type: vmRequest.size, vpc: vmRequest.vpc, subnet: vmRequest.subnet, security_group: vmRequest.security, storage_gib: Number(vmRequest.storage), environment: vmRequest.environment, instance_profile: "OpsAgentManagedInstanceProfile", key_name: vmRequest.keyName || null };
    setBusy(true);
    try {
      setVmPreview(await api<Record<string, unknown>>("/operations/aws/provision/preview", { method: "POST", body: JSON.stringify(payload) }));
      setVmConfirmation(""); setVmResult(null); setVmError("");
    } catch (error) { setVmError((error as Error).message); }
    finally { setBusy(false); }
  }
  async function executeVmProvision() {
    if (!vmPreview || vmConfirmation !== String(vmPreview.approval_phrase) || busy) return;
    const payload = { name: vmRequest.name, region: vmRequest.region, os: vmRequest.os, instance_type: vmRequest.size, vpc: vmRequest.vpc, subnet: vmRequest.subnet, security_group: vmRequest.security, storage_gib: Number(vmRequest.storage), environment: vmRequest.environment, instance_profile: "OpsAgentManagedInstanceProfile", key_name: vmRequest.keyName || null, confirmation: vmConfirmation };
    setBusy(true);
    setVmError("");
    try { setVmResult(await api<Record<string, unknown>>("/operations/aws/provision/execute", { method: "POST", body: JSON.stringify(payload) })); }
    catch (error) { setVmError((error as Error).message); }
    finally { setBusy(false); }
  }
  async function approveTermination(requestId: string) {
    setTerminationResults((current)=>({...current,[requestId]:"Verifying MFA and policy…"}));
    try {
      const result = await api<Record<string,unknown>>(`/chat/terminations/${requestId}/approve`, {method:"POST", body:JSON.stringify({session_id:session,mfa_code:terminationCodes[requestId] || "",backup_confirmed:!!terminationBackups[requestId]})});
      setTerminationResults((current)=>({...current,[requestId]:`Termination accepted · ${String(result.instance_id || requestId)}`}));
    } catch (error) { setTerminationResults((current)=>({...current,[requestId]:(error as Error).message})); }
  }
  async function newChat() {
    const made = await api<{ session_id: string }>("/chat/sessions", {
      method: "POST",
    });
    setMessages([]);
    setAttachments([]);
    refresh(made.session_id);
  }
  async function removeChat(id: string) {
    await api(`/chat/sessions/${id}`, { method: "DELETE" });
    setSession("");
    setMessages([]);
    refresh();
  }
  return (
    <section className="chat-shell">
      <aside className="chat-history">
        <button className="new-chat" onClick={newChat}>
          ＋ New chat
        </button>
        <p>RECENT</p>
        {sessions.map((x) => (
          <button
            className={session === x.session_id ? "selected" : ""}
            onClick={() => setSession(x.session_id)}
            key={x.session_id}
          >
            <MessageSquare />
            <span>{x.title}</span>
            <Trash2
              onClick={(e) => {
                e.stopPropagation();
                removeChat(x.session_id);
              }}
            />
          </button>
        ))}
      </aside>
      <div className="chat-main">
        <div className="messages">
          {!messages.length && !provisionOpen && (
            <div className="chat-welcome">
              <OpsLogo />
              <h2>How can OpsAgent help?</h2>
              <p>
                Ask about infrastructure, upload logs or configuration,
                investigate inventory, or plan an approved operation.
              </p>
              <div className="chat-quick-actions"><button onClick={() => setProvisionOpen(true)}><Server/><span><b>Create an AWS VM</b><small>Guided EC2 provisioning with approval</small></span><ChevronRight/></button><button onClick={() => setText("Show the current AWS server inventory and health.")}><Cloud/><span><b>Review AWS estate</b><small>Inventory, state and operational health</small></span><ChevronRight/></button></div>
            </div>
          )}
          {provisionOpen && (
            <form ref={guidedForm} className="guided-operation" onSubmit={sendVmRequest}>
              <header><div><span>GUIDED OPERATION · AWS</span><h3>Provision an EC2 virtual machine</h3><p>Choose the required configuration. OpsAgent validates it and prepares approval before any change is made.</p></div><button type="button" onClick={() => setProvisionOpen(false)} aria-label="Close"><X /></button></header>
              <div className="guided-grid">
                {awsOptionsError && <div className="guided-connection-error"><AlertTriangle/><div><b>AWS connection unavailable</b><span>{awsOptionsError}</span></div></div>}
                <label className="wide">Instance name<input required value={vmRequest.name} onChange={(e) => setVmRequest({...vmRequest,name:e.target.value})} placeholder="for example: finance-app-01" /></label>
                <label>Region<select value={vmRequest.region} onChange={(e) => setVmRequest({...vmRequest,region:e.target.value})}><option>us-east-1</option><option>us-east-2</option><option>us-west-2</option><option>ap-south-1</option><option>eu-west-1</option></select></label>
                <label>Environment<select value={vmRequest.environment} onChange={(e) => setVmRequest({...vmRequest,environment:e.target.value})}><option>Development</option><option>Test</option><option>Staging</option><option>Production</option></select></label>
                <label>Operating system<select value={vmRequest.os} onChange={(e) => setVmRequest({...vmRequest,os:e.target.value})}><option>Windows Server 2022</option><option>Windows Server 2025</option><option>Amazon Linux 2023</option><option>Ubuntu Server 24.04 LTS</option><option>Red Hat Enterprise Linux 9</option></select></label>
                <label>Instance type<select value={vmRequest.size} onChange={(e) => setVmRequest({...vmRequest,size:e.target.value})}><option>t3.small</option><option>t3.medium</option><option>t3.large</option><option>m6i.large</option><option>m6i.xlarge</option></select></label>
                <label>VPC<select value={vmRequest.vpc} onChange={(e) => setVmRequest({...vmRequest,vpc:e.target.value,subnet:"",security:""})}>{awsOptions?.vpcs.map((item)=><option value={item.id} key={item.id}>{item.name} · {item.cidr}</option>) || <option>Loading connected AWS account…</option>}</select></label>
                <label>Subnet<select value={vmRequest.subnet} onChange={(e) => setVmRequest({...vmRequest,subnet:e.target.value})}>{awsOptions?.subnets.filter((item)=>item.vpc_id===vmRequest.vpc).map((item)=><option value={item.id} key={item.id}>{item.name} · {item.zone} · {item.public?"public":"private"}</option>) || <option>Loading subnets…</option>}</select></label>
                <label>Security group<select value={vmRequest.security} onChange={(e) => setVmRequest({...vmRequest,security:e.target.value})}>{awsOptions?.security_groups.filter((item)=>item.vpc_id===vmRequest.vpc).map((item)=><option value={item.id} key={item.id}>{item.name} · {item.id}</option>) || <option>Loading security groups…</option>}</select></label>
                <label>Encrypted storage (GiB)<input type="number" min="30" max="16384" value={vmRequest.storage} onChange={(e) => setVmRequest({...vmRequest,storage:e.target.value})} /></label>
                <label>Access method<select value={vmRequest.access} onChange={(e) => setVmRequest({...vmRequest,access:e.target.value})}><option>AWS Systems Manager</option><option>RDP through approved bastion</option><option>SSH through approved bastion</option></select></label>
                <label>AWS key pair<select value={vmRequest.keyName} onChange={(e) => setVmRequest({...vmRequest,keyName:e.target.value})}><option value="">No key pair · Systems Manager only</option>{awsOptions?.key_pairs.map((item)=><option value={item.name} key={item.name}>{item.name}</option>)}</select><small className="field-help">OpsAgent uses only the key-pair name. Never upload a private PEM file.</small></label>
                <label>Monitoring<select value={vmRequest.monitoring} onChange={(e) => setVmRequest({...vmRequest,monitoring:e.target.value})}><option>CloudWatch enabled</option><option>Standard platform monitoring</option><option>Not required</option></select></label>
                <label>Backup policy<select value={vmRequest.backup} onChange={(e) => setVmRequest({...vmRequest,backup:e.target.value})}><option>Daily snapshot</option><option>Weekly snapshot</option><option>Organization backup policy</option><option>Not required</option></select></label>
              </div>
              {!vmPreview && <footer><span><ShieldCheck /> No resource is created during validation</span><button className="primary-action" disabled={busy || !vmRequest.name.trim() || !!awsOptionsError || !awsOptions}>{busy ? "Validating…" : "Validate and review"}<ChevronRight /></button></footer>}
              {vmPreview && <section className="provision-review">
                <header><CheckCircle2/><div><b>AWS validation passed</b><span>Review the exact resources before approval</span></div></header>
                <dl><div><dt>AMI</dt><dd>{String(vmPreview.ami_name)}<small>{String(vmPreview.ami_id)}</small></dd></div><div><dt>Network</dt><dd>{String(vmPreview.subnet_id)}<small>{String(vmPreview.vpc_id)}</small></dd></div><div><dt>Security group</dt><dd>{String(vmPreview.security_group_id)}</dd></div><div><dt>Compute</dt><dd>{String(vmPreview.instance_type)}<small>{String(vmPreview.storage_gib)} GiB encrypted gp3</small></dd></div><div><dt>Access</dt><dd>{vmPreview.key_name ? String(vmPreview.key_name) : "Systems Manager only"}<small>{vmPreview.key_name ? "Existing AWS key pair" : "No PEM key required"}</small></dd></div></dl>
                <div className="approval-entry"><span>Type this exact approval phrase</span><code>{String(vmPreview.approval_phrase)}</code><input value={vmConfirmation} onChange={(e)=>setVmConfirmation(e.target.value)} placeholder="Enter approval phrase" /></div>
                {vmError && <div className="provision-error"><AlertTriangle/><div><b>Provisioning was blocked</b><span>{vmError}</span></div></div>}
                {vmResult ? <div className="provision-result"><CheckCircle2/><div><b>{vmResult.dry_run ? "Dry-run validation completed" : "Instance provisioned"}</b><span>{String(vmResult.instance_id || vmResult.message || "AWS accepted the operation")}</span></div></div> : <footer><button type="button" onClick={()=>setVmPreview(null)}>Edit request</button><button type="button" className="primary-action" onClick={executeVmProvision} disabled={busy || vmConfirmation !== String(vmPreview.approval_phrase)}>{busy ? "Provisioning…" : "Approve and provision"}<ShieldCheck/></button></footer>}
              </section>}
            </form>
          )}
          {messages.map((m, i) => { const terminationId = m.role === "assistant" && /Action:\s*(?:Terminate Instance|Permanently terminate)/i.test(m.content) ? m.content.match(/Request ID:\s*(CHAT-[0-9A-F]{8})/i)?.[1]?.toUpperCase() : undefined; return (
            <article className={`message ${m.role}`} key={i}>
              <b>{m.role === "user" ? "You" : "OpsAgent"}</b>
              <p>{m.content}</p>
              {terminationId && <section className="termination-approval"><header><AlertTriangle/><div><strong>Permanent AWS termination</strong><span>Admin + MFA required · irreversible operation</span></div></header><label><input type="checkbox" checked={!!terminationBackups[terminationId]} onChange={(e)=>setTerminationBackups((current)=>({...current,[terminationId]:e.target.checked}))}/><span>I confirm the required backup or snapshot is complete.</span></label><label>Authenticator code<input inputMode="numeric" maxLength={6} value={terminationCodes[terminationId] || ""} onChange={(e)=>setTerminationCodes((current)=>({...current,[terminationId]:e.target.value.replace(/\D/g,"").slice(0,6)}))} placeholder="6-digit code"/></label><button disabled={!terminationBackups[terminationId] || (terminationCodes[terminationId] || "").length !== 6} onClick={()=>approveTermination(terminationId)}><ShieldCheck/>Verify MFA and terminate</button>{terminationResults[terminationId] && <p>{terminationResults[terminationId]}</p>}</section>}
            </article>
          )})}
          {busy && !provisionOpen && (
            <article className="message assistant">
              <b>OpsAgent</b>
              <p>Analyzing your infrastructure…</p>
            </article>
          )}
        </div>
        <form className="composer chatgpt" onSubmit={send}>
          {attachments.length > 0 && (
            <div className="attachment-list">
              {attachments.map((a, i) => (
                <span key={i}>
                  <Paperclip />
                  {a.name}
                  <X
                    onClick={() =>
                      setAttachments((x) => x.filter((_, n) => n !== i))
                    }
                  />
                </span>
              ))}
            </div>
          )}
          <div className="composer-row">
            <input
              ref={fileInput}
              type="file"
              multiple
              hidden
              onChange={(e) => addFiles(e.target.files)}
            />
            <button
              type="button"
              className="attach"
              onClick={() => fileInput.current?.click()}
              title="Attach files"
            >
              <Paperclip />
            </button>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder={listening ? "Listening… speak now" : "Ask anything"}
              aria-label="Chat message"
              rows={1}
            />
            <button
              type="button"
              className={`voice-control ${listening === "dictation" ? "recording" : ""}`}
              onClick={() => listen("dictation")}
              title="Dictate a message"
              aria-label="Dictate a message"
            >
              <Mic />
            </button>
            <button
              type="button"
              className={`voice-control voice-mode ${listening === "voice" ? "recording" : ""}`}
              onClick={() => listen("voice")}
              title={
                listening === "voice"
                  ? "Stop voice recording"
                  : "Start voice recording"
              }
              aria-label="Voice recording"
            >
              <AudioLines />
            </button>
            <button className="send" disabled={busy || (!text.trim() && !attachments.length)} title="Send message">
              <Send />
            </button>
          </div>
          <div className="composer-footer">
            <select
              value={persona}
              onChange={(e) => setPersona(e.target.value)}
            >
              <option>Senior Infrastructure Architect</option>
              <option>AWS Cloud Architect</option>
              <option>Windows & SCCM Expert</option>
              <option>VMware & Hardware Expert</option>
              <option>Linux & Automation Expert</option>
              <option>Network & Security Architect</option>
            </select>
            <small>
              OpsAgent can make mistakes. Review operations before approval.
            </small>
          </div>
        </form>
      </div>
    </section>
  );
}

function AwsOperations({ servers }: { servers: Machine[] }) {
  const [action, setAction] = useState("start_instance");
  const [target, setTarget] = useState(servers[0]?.aws_instance_id || "");
  const [confirmation, setConfirmation] = useState("");
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);
  const expected = `CONFIRM ${action.toUpperCase()} ${target}`;
  async function execute(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setResult("");
    try {
      const value = await api<Record<string, unknown>>(
        "/operations/aws/execute",
        {
          method: "POST",
          body: JSON.stringify({ action, identifier: target, confirmation }),
        },
      );
      setResult(
        `Operation accepted: ${String(value.after_status || value.message || "success")}`,
      );
    } catch (e) {
      setResult((e as Error).message);
    } finally {
      setConfirmation("");
      setBusy(false);
    }
  }
  return (
    <div className="operations-grid">
      <section className="panel">
        <div className="panel-title">
          <h3>Guarded AWS operation</h3>
          <span>RBAC + confirmation + audit</span>
        </div>
        <form className="operation-form" onSubmit={execute}>
          <label>
            Action
            <select
              value={action}
              onChange={(e) => {
                setAction(e.target.value);
                setConfirmation("");
              }}
            >
              <option value="start_instance">Start instance</option>
              <option value="stop_instance">Stop instance</option>
              <option value="reboot_instance">Reboot instance</option>
              <option value="terminate_instance">Terminate instance</option>
            </select>
          </label>
          <label>
            Target
            <select
              value={target}
              onChange={(e) => {
                setTarget(e.target.value);
                setConfirmation("");
              }}
            >
              {servers.map((s) => (
                <option value={s.aws_instance_id} key={s.aws_instance_id}>
                  {s.server_name} · {s.aws_instance_id}
                </option>
              ))}
            </select>
          </label>
          <div className="confirmation">
            To approve, type: <code>{expected}</code>
          </div>
          <label>
            Confirmation
            <input
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
            />
          </label>
          <button disabled={busy || confirmation !== expected}>
            {busy ? "Executing…" : "Execute approved operation"}
          </button>
          {result && <p className="notice">{result}</p>}
        </form>
      </section>
      <RemoteWorkspace
        endpoint="/operations/aws/audit"
        title="AWS operation audit"
      />
    </div>
  );
}

const WINDOWS_OPERATION_GROUPS: { category: string; icon: LucideIcon; actions: string[] }[] = [
  { category: "Active Directory", icon: Users, actions: ["Create domain", "Add domain controller", "Create organizational unit", "Create security group", "Join computer to domain", "Move computer account", "Reset computer trust", "Configure sites and services", "Create group policy", "Link group policy", "Force replication", "Transfer FSMO roles"] },
  { category: "Users and access", icon: KeyRound, actions: ["Create domain user", "Disable user", "Enable user", "Reset password", "Unlock account", "Add user to group", "Remove user from group", "Set account expiry", "Configure service account", "Create managed service account", "Review privileged membership", "Remove stale accounts"] },
  { category: "DNS management", icon: Cloud, actions: ["Create DNS zone", "Delete DNS zone", "Create A record", "Create AAAA record", "Create CNAME record", "Create PTR record", "Create MX record", "Update DNS record", "Delete DNS record", "Configure forwarder", "Clear DNS cache", "Validate DNS resolution"] },
  { category: "DHCP management", icon: Cable, actions: ["Create DHCP scope", "Modify DHCP scope", "Activate scope", "Deactivate scope", "Delete DHCP scope", "Create reservation", "Update reservation", "Delete reservation", "Exclude IP range", "Create scope option", "Reconcile scope", "Review lease utilization"] },
  { category: "Certificates and PKI", icon: ShieldCheck, actions: ["Install certificate", "Renew certificate", "Remove certificate", "Create certificate request", "Import PFX certificate", "Export public certificate", "Bind certificate to service", "Replace expiring certificate", "Validate certificate chain", "Publish certificate template", "Revoke certificate", "Audit certificate expiry"] },
  { category: "Windows Server", icon: Server, actions: ["Install Windows feature", "Remove Windows feature", "Start service", "Stop service", "Restart service", "Configure service recovery", "Create scheduled task", "Remove scheduled task", "Set environment variable", "Configure time synchronization", "Update server name", "Restart server"] },
  { category: "Patching and upgrades", icon: RefreshCw, actions: ["Assess missing updates", "Install security updates", "Install cumulative update", "Schedule patch window", "Pause Windows Update", "Resume Windows Update", "Upgrade Windows Server", "Run pre-upgrade checks", "Run post-patch validation", "Rollback update", "Coordinate SCCM deployment", "Verify patch compliance"] },
  { category: "Storage and file services", icon: Database, actions: ["Initialize disk", "Create volume", "Extend volume", "Format volume", "Assign drive letter", "Create SMB share", "Update share permissions", "Update NTFS permissions", "Enable file screening", "Configure DFS namespace", "Configure DFS replication", "Review disk capacity"] },
  { category: "IIS and applications", icon: Boxes, actions: ["Create IIS website", "Create application pool", "Deploy web application", "Start application pool", "Recycle application pool", "Stop website", "Configure binding", "Configure HTTPS binding", "Update web configuration", "Collect IIS logs", "Test application endpoint", "Rollback deployment"] },
  { category: "Security and compliance", icon: ShieldCheck, actions: ["Configure Windows Firewall rule", "Remove firewall rule", "Enable Defender scan", "Run malware scan", "Configure audit policy", "Review local administrators", "Rotate local administrator password", "Apply security baseline", "Enable BitLocker", "Collect compliance evidence", "Review failed logons", "Quarantine server"] },
  { category: "Troubleshooting and recovery", icon: MonitorCog, actions: ["Collect event logs", "Check service health", "Check port connectivity", "Trace DNS failure", "Analyze high CPU", "Analyze memory pressure", "Analyze disk latency", "Collect performance counters", "Repair Windows component store", "Run system file check", "Restore service configuration", "Validate recovery"] },
];

const operationSlug = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
const WINDOWS_FEATURE_OPTIONS = [
  ["Active Directory Domain Services", "AD-Domain-Services"],
  ["Active Directory Certificate Services", "AD-Certificate"],
  ["DNS Server", "DNS"],
  ["DHCP Server", "DHCP"],
  ["Web Server (IIS)", "Web-Server"],
  ["IIS Management Tools", "Web-Mgmt-Tools"],
  ["File and Storage Services", "File-Services"],
  ["File Server", "FS-FileServer"],
  ["DFS Namespaces", "FS-DFS-Namespace"],
  ["DFS Replication", "FS-DFS-Replication"],
  ["Failover Clustering", "Failover-Clustering"],
  ["Hyper-V", "Hyper-V"],
  ["Network Load Balancing", "NLB"],
  ["Remote Desktop Services", "Remote-Desktop-Services"],
  ["Windows Server Backup", "Windows-Server-Backup"],
  ["BitLocker Drive Encryption", "BitLocker"],
  ["Containers", "Containers"],
  ["OpenSSH Server", "OpenSSH-Server"],
  ["RSAT Active Directory Tools", "RSAT-AD-Tools"],
  ["RSAT DNS Server Tools", "RSAT-DNS-Server"],
  ["RSAT DHCP Server Tools", "RSAT-DHCP"],
] as const;
const operationParameters = (action: string): Record<string, string> => {
  const value = action.toLowerCase();
  if (value === "install windows feature" || value === "remove windows feature") return { FeatureName: "AD-Domain-Services", IncludeAllSubFeature: "false", IncludeManagementTools: "true", RestartIfRequired: "false" };
  if (value === "join computer to domain") return { DomainName: "opsagent.test", DomainCredentialSecretId: "opsagent/domain-join/service-account", OrganizationalUnitPath: "OU=opsone_Servers,DC=opsagent,DC=test", RestartIfRequired: "true" };
  if (value.includes("domain") && value.includes("user")) return { UserName: "", SecretId: "", OrganizationalUnit: "", GroupName: "" };
  if (value === "create domain") return { DomainName: "", NetBIOSName: "", SafeModeSecretId: "", InstallDns: "true", RestartIfRequired: "true" };
  if (value.includes("dns") || value.includes("record")) return { ZoneName: "", Name: "", IPv4Address: "" };
  if (value.includes("dhcp scope")) return { ScopeName: "", StartRange: "", EndRange: "", SubnetMask: "" };
  if (value.includes("reservation")) return { ScopeId: "", IPAddress: "", ClientId: "", Name: "" };
  if (value.includes("user") || value.includes("account")) return { UserName: "", SecretId: "", GroupName: "" };
  if (value.includes("service")) return { ServiceName: "" };
  if (value.includes("package")) return { PackageName: "" };
  if (value.includes("certificate")) return { CertificateS3Uri: "", StoreName: "My" };
  return {};
};

const OPERATION_FIELD_DETAILS: Record<string, { label: string; placeholder: string; optional?: boolean }> = {
  DomainName: { label: "Active Directory domain", placeholder: "Example: corp.example.com" },
  DomainCredentialSecretId: { label: "AWS Secrets Manager credential", placeholder: "Example: opsagent/domain-join/service-account" },
  OrganizationalUnitPath: { label: "Computer OU path", placeholder: "Optional: OU=Servers,DC=corp,DC=example,DC=com", optional: true },
  RestartIfRequired: { label: "Restart if required", placeholder: "" },
};

const OPERATION_FIELD_OPTIONS: Record<string, { value: string; label: string }[]> = {
  DomainName: [{ value: "opsagent.test", label: "opsagent.test" }],
  DomainCredentialSecretId: [{ value: "opsagent/domain-join/service-account", label: "OpsAgent domain-join service account" }],
  OrganizationalUnitPath: [{ value: "OU=opsone_Servers,DC=opsagent,DC=test", label: "opsone_Servers" }],
};

function SsmExecutionPanel({ action, platform, servers, onClose }: { action: string; platform: "Windows" | "Linux"; servers: Machine[]; onClose: () => void }) {
  const slug = operationSlug(action);
  const parameterTemplate = operationParameters(action);
  const guidedParameterNames = Object.keys(parameterTemplate);
  const [target, setTarget] = useState(servers[0]?.aws_instance_id || "");
  const [parameterValues, setParameterValues] = useState<Record<string, string>>(parameterTemplate);
  const [advancedParameters, setAdvancedParameters] = useState("{}");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const expected = `CONFIRM ${slug.toUpperCase()} ${target}`;
  useEffect(() => {
    if (!busy) return;
    setElapsedSeconds(0);
    const started = Date.now();
    const timer = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);
  const execute = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(""); setResult(null);
    try {
      const parsed = guidedParameterNames.length ? parameterValues : JSON.parse(advancedParameters || "{}");
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("Parameters must be a JSON object");
      const missing = guidedParameterNames.filter((name) => !name.startsWith("Include") && !name.startsWith("Restart") && !OPERATION_FIELD_DETAILS[name]?.optional && !String(parsed[name] ?? "").trim());
      if (missing.length) throw new Error(`Complete required field${missing.length === 1 ? "" : "s"}: ${missing.join(", ")}`);
      if (slug === "join_computer_to_domain" && String(parsed.DomainCredentialSecretId || "").startsWith("arn:aws:iam:")) throw new Error("Choose an AWS Secrets Manager secret. An IAM role ARN is not a domain credential secret.");
      if (slug === "join_computer_to_domain" && !String(parsed.DomainCredentialSecretId || "").includes("opsagent/domain-join/")) throw new Error("Choose the OpsAgent domain-join credential from the secret dropdown.");
      setResult(await api<Record<string, unknown>>("/operations/ssm/execute", { method: "POST", body: JSON.stringify({ action: slug, instance_id: target, confirmation, parameters: parsed }) }));
    } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); }
  };
  return <section className="ssm-execution-panel"><header><div className={`ssm-platform-icon ${platform.toLowerCase()}`}>{platform === "Windows" ? <FaWindows /> : <SiLinux />}</div><div><span>APPROVAL-GATED SSM RUNBOOK</span><h3>{action}</h3><p>Executes document <code>OpsAgent-{slug}</code> on an online SSM-managed {platform} server.</p></div><button onClick={onClose}><X /></button></header>
    <form onSubmit={execute}><label>Target server<select value={target} onChange={(event) => { setTarget(event.target.value); setConfirmation(""); }}>{servers.length ? servers.map((server) => <option key={server.aws_instance_id} value={server.aws_instance_id}>{server.server_name} · {server.aws_instance_id} · {server.os_version || platform}</option>) : <option value="">No matching SSM inventory target</option>}</select></label>{guidedParameterNames.length ? <fieldset className="ssm-guided-parameters"><legend>Operation details</legend>{guidedParameterNames.map((name) => { const isChoice = ["true", "false"].includes(parameterValues[name]); const details = OPERATION_FIELD_DETAILS[name]; const fieldOptions = OPERATION_FIELD_OPTIONS[name]; const label = details?.label || name.replace(/([a-z])([A-Z])/g, "$1 $2"); return <label key={name}>{label}{details?.optional && <small>Optional</small>}{name === "FeatureName" ? <select value={parameterValues[name]} onChange={(event) => setParameterValues((current) => ({ ...current, [name]: event.target.value }))}>{WINDOWS_FEATURE_OPTIONS.map(([friendlyName, featureName]) => <option key={featureName} value={featureName}>{friendlyName} · {featureName}</option>)}</select> : fieldOptions ? <select value={parameterValues[name]} onChange={(event) => setParameterValues((current) => ({ ...current, [name]: event.target.value }))}>{fieldOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select> : isChoice ? <select value={parameterValues[name]} onChange={(event) => setParameterValues((current) => ({ ...current, [name]: event.target.value }))}><option value="true">Yes</option><option value="false">No</option></select> : <input value={parameterValues[name]} onChange={(event) => setParameterValues((current) => ({ ...current, [name]: event.target.value }))} placeholder={details?.placeholder || `Enter ${label.toLowerCase()}`} />}</label>; })}</fieldset> : <label>Advanced runbook parameters (JSON)<textarea value={advancedParameters} onChange={(event) => setAdvancedParameters(event.target.value)} spellCheck={false} placeholder="{}" /></label>}<div className="ssm-confirm"><span>Type this exact approval phrase</span><code>{expected || "Select a target"}</code><input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder="Paste confirmation phrase" /></div><button className="ssm-execute" disabled={busy || !target || confirmation !== expected}>{busy ? "Executing and verifying…" : "Approve and execute runbook"}</button></form>
    {busy && <section className="ssm-live-progress" aria-live="polite"><header><div><strong>Operation in progress</strong><span>Elapsed {elapsedSeconds}s · Keep this page open</span></div><b><RefreshCw /> Live</b></header><div className="ssm-progress-steps">{[
      ["Request approved", true],
      ["Target validated", elapsedSeconds >= 1],
      ["Command dispatched", elapsedSeconds >= 2],
      ["Runbook executing", elapsedSeconds >= 3],
      ["Verifying result", elapsedSeconds >= 8],
    ].map(([label, active], index) => <div className={active ? "active" : "pending"} key={String(label)}><i>{active ? <CheckCircle2 /> : index + 1}</i><span>{label}</span>{active && index === Math.min(4, elapsedSeconds < 1 ? 0 : elapsedSeconds < 2 ? 1 : elapsedSeconds < 3 ? 2 : elapsedSeconds < 8 ? 3 : 4) && <em>In progress</em>}</div>)}</div></section>}
    {error && <div className="ssm-result error"><AlertTriangle /><div><strong>Execution blocked or failed</strong><pre>{error}</pre></div></div>}{result && <section className="ssm-completion-report"><header><CheckCircle2 /><div><strong>{result.dry_run ? "Dry-run validation completed" : "Operation completed and verified"}</strong><span>{String(result.status || "Success")} · {String(result.completed_at || "Completed now")}</span></div></header><div className="ssm-result-facts"><div><span>Operation</span><b>{String(result.action || slug).replaceAll("_", " ")}</b></div><div><span>Target server</span><b>{String(result.instance_id || target)}</b></div><div><span>Request ID</span><b>{String(result.request_id || "—")}</b></div><div><span>SSM command ID</span><b>{String(result.command_id || "—")}</b></div></div>{Boolean(result.stdout) && <div className="ssm-command-output"><span>Verification output</span><pre>{String(result.stdout)}</pre></div>}{Boolean(result.stderr) && <div className="ssm-command-output error"><span>Command warnings or errors</span><pre>{String(result.stderr)}</pre></div>}</section>}
  </section>;
}

function WindowsOperations({ servers }: { servers: Machine[] }) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [selectedOperation, setSelectedOperation] = useState("");
  const normalized = search.trim().toLowerCase();
  const groups = WINDOWS_OPERATION_GROUPS.map((group) => ({ ...group, actions: group.actions.filter((action) => !normalized || `${group.category} ${action}`.toLowerCase().includes(normalized)) })).filter((group) => group.actions.length && (category === "All" || group.category === category));
  const total = WINDOWS_OPERATION_GROUPS.reduce((count, group) => count + group.actions.length, 0);
  return <section className="windows-operations-page">
    <section className="windows-operations-lead"><div className="windows-lead-mark"><FaWindows /></div><div><span>WINDOWS AUTOMATION CATALOG</span><h2>Windows operations</h2><p>Search, request and approve common Windows Server, Active Directory, DNS, DHCP, certificate, patching and recovery work.</p></div><strong>{total}+ operations</strong></section>
    <section className="request-channel-strip"><span>Requests can enter through</span><b><Bot /> OpsAgent Chat</b><b><FaSlack /> Slack</b><b><SiGmail /> Gmail</b><b><Mail /> Outlook</b><em>Every change requires target validation, approval and verification.</em></section>
    <section className="windows-catalog-toolbar"><label><Search /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search Windows operations…" /></label><select value={category} onChange={(event) => setCategory(event.target.value)}><option>All</option>{WINDOWS_OPERATION_GROUPS.map((group) => <option key={group.category}>{group.category}</option>)}</select><span>{groups.reduce((count, group) => count + group.actions.length, 0)} matching operations</span></section>
    {selectedOperation && <SsmExecutionPanel key={selectedOperation} action={selectedOperation} platform="Windows" servers={servers} onClose={() => setSelectedOperation("")} />}
    <div className="windows-operation-groups">{groups.map((group) => { const Icon = group.icon; return <article key={group.category}><header><i><Icon /></i><div><h3>{group.category}</h3><span>{group.actions.length} operations</span></div></header><div>{group.actions.map((action) => <button key={action} onClick={() => { setSelectedOperation(action); window.scrollTo({ top: 0, behavior: "smooth" }); }}><span>{action}</span><small>Configure and execute</small><ChevronRight /></button>)}</div></article>; })}</div>
    <RemoteWorkspace endpoint="/operations/ssm/audit" title="Windows and Linux operation audit" />
  </section>;
}

const LINUX_OPERATION_GROUPS: { category: string; icon: LucideIcon; actions: string[] }[] = [
  { category: "Users and access", icon: Users, actions: ["Create local user", "Disable user", "Enable user", "Delete user", "Reset password", "Expire password", "Add user to group", "Remove user from group", "Configure sudo access", "Create service account", "Deploy SSH public key", "Audit privileged access"] },
  { category: "Packages and repositories", icon: Boxes, actions: ["Install package", "Remove package", "Update package", "Upgrade all packages", "Add package repository", "Remove package repository", "Refresh repository metadata", "Pin package version", "Verify package signature", "List installed packages", "Repair package database", "Audit vulnerable packages"] },
  { category: "Services and processes", icon: Cpu, actions: ["Start service", "Stop service", "Restart service", "Reload service", "Enable service at boot", "Disable service at boot", "Create systemd service", "Update systemd unit", "Inspect failed services", "Terminate process", "Adjust process priority", "Collect process diagnostics"] },
  { category: "Networking and DNS", icon: Cable, actions: ["Configure static IP", "Add secondary IP", "Remove IP address", "Configure default route", "Add static route", "Remove static route", "Configure DNS resolver", "Update hosts entry", "Test DNS resolution", "Check port connectivity", "Configure network interface", "Restart network service"] },
  { category: "Storage and filesystems", icon: Database, actions: ["Discover disks", "Create partition", "Create filesystem", "Mount filesystem", "Unmount filesystem", "Extend logical volume", "Extend filesystem", "Create LVM volume group", "Create logical volume", "Configure persistent mount", "Check filesystem health", "Audit disk utilization"] },
  { category: "Security and firewall", icon: ShieldCheck, actions: ["Create firewall rule", "Remove firewall rule", "Open service port", "Close service port", "Configure SELinux mode", "Restore SELinux context", "Configure AppArmor profile", "Run malware scan", "Audit failed logins", "Lock compromised account", "Apply security baseline", "Collect compliance evidence"] },
  { category: "Certificates and encryption", icon: KeyRound, actions: ["Install TLS certificate", "Renew TLS certificate", "Remove certificate", "Generate private key", "Create certificate request", "Import CA certificate", "Update trust store", "Validate certificate chain", "Check certificate expiry", "Configure automated renewal", "Encrypt data volume", "Rotate encryption key"] },
  { category: "Patching and upgrades", icon: RefreshCw, actions: ["Assess missing patches", "Install security patches", "Schedule patch window", "Create pre-patch snapshot", "Run pre-patch checks", "Patch selected packages", "Upgrade Linux distribution", "Upgrade kernel", "Schedule reboot", "Run post-patch validation", "Rollback package", "Verify patch compliance"] },
  { category: "Web and application services", icon: Cloud, actions: ["Install NGINX", "Configure NGINX virtual host", "Reload NGINX", "Install Apache", "Configure Apache virtual host", "Reload Apache", "Deploy application artifact", "Update application configuration", "Configure reverse proxy", "Configure TLS binding", "Test application endpoint", "Rollback application deployment"] },
  { category: "Database operations", icon: Database, actions: ["Check database service", "Start database service", "Stop database service", "Restart database service", "Create database backup", "Verify database backup", "Check replication health", "Check database connectivity", "Collect slow-query evidence", "Rotate database logs", "Check database capacity", "Run database recovery validation"] },
  { category: "Monitoring and troubleshooting", icon: MonitorCog, actions: ["Install monitoring agent", "Restart monitoring agent", "Collect system logs", "Collect journal logs", "Analyze high CPU", "Analyze memory pressure", "Analyze disk latency", "Analyze load average", "Trace network path", "Capture network packets", "Collect performance snapshot", "Validate service recovery"] },
];

function LinuxOperations({ servers }: { servers: Machine[] }) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [selectedOperation, setSelectedOperation] = useState("");
  const normalized = search.trim().toLowerCase();
  const groups = LINUX_OPERATION_GROUPS.map((group) => ({ ...group, actions: group.actions.filter((action) => !normalized || `${group.category} ${action}`.toLowerCase().includes(normalized)) })).filter((group) => group.actions.length && (category === "All" || group.category === category));
  const total = LINUX_OPERATION_GROUPS.reduce((count, group) => count + group.actions.length, 0);
  return <section className="windows-operations-page linux-operations-page">
    <section className="windows-operations-lead"><div className="windows-lead-mark linux"><SiLinux /></div><div><span>LINUX AUTOMATION CATALOG</span><h2>Linux operations</h2><p>Search, request and approve common Linux administration, patching, security, application and recovery work across supported distributions.</p></div><strong>{total}+ operations</strong></section>
    <section className="request-channel-strip"><span>Requests can enter through</span><b><Bot /> OpsAgent Chat</b><b><FaSlack /> Slack</b><b><SiGmail /> Gmail</b><b><Mail /> Outlook</b><em>Commands run through an approved host agent or enterprise runbook with complete evidence.</em></section>
    <section className="windows-catalog-toolbar"><label><Search /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search Linux operations…" /></label><select value={category} onChange={(event) => setCategory(event.target.value)}><option>All</option>{LINUX_OPERATION_GROUPS.map((group) => <option key={group.category}>{group.category}</option>)}</select><span>{groups.reduce((count, group) => count + group.actions.length, 0)} matching operations</span></section>
    {selectedOperation && <SsmExecutionPanel key={selectedOperation} action={selectedOperation} platform="Linux" servers={servers} onClose={() => setSelectedOperation("")} />}
    <div className="windows-operation-groups">{groups.map((group) => { const Icon = group.icon; return <article key={group.category}><header><i><Icon /></i><div><h3>{group.category}</h3><span>{group.actions.length} operations</span></div></header><div>{group.actions.map((action) => <button key={action} onClick={() => { setSelectedOperation(action); window.scrollTo({ top: 0, behavior: "smooth" }); }}><span>{action}</span><small>Configure and execute</small><ChevronRight /></button>)}</div></article>; })}</div>
    <RemoteWorkspace endpoint="/operations/ssm/audit" title="Windows and Linux operation audit" />
  </section>;
}

function AwsOperationsV2({ servers, user, onNavigate }: { servers: Machine[]; user: User; onNavigate?: (page: string) => void }) {
  const [inventory, setInventory] = useState(servers);
  const [syncingInventory, setSyncingInventory] = useState(false);
  const [inventoryMessage, setInventoryMessage] = useState("");
  const [action, setAction] = useState("");
  const [target, setTarget] = useState("");
  const [selectedTargets, setSelectedTargets] = useState<string[]>([]);
  const [instanceFilter, setInstanceFilter] = useState<"all"|"running"|"stopped">("all");
  const [confirmation, setConfirmation] = useState("");
  const [instanceType, setInstanceType] = useState("t3.small");
  const [volume, setVolume] = useState("");
  const [size, setSize] = useState(40);
  const [audit, setAudit] = useState<{events: Record<string, unknown>[]} | null>(null);
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);
  const [operationStarted, setOperationStarted] = useState(false);
  const [showLiveTrail, setShowLiveTrail] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [progressStage, setProgressStage] = useState(0);
  const operationPanel = useRef<HTMLElement | null>(null);
  useEffect(() => { setInventory(servers); }, [servers]);
  const loadAudit = () => api<{events: Record<string, unknown>[]}>("/operations/aws/audit").then(setAudit);
  useEffect(() => { loadAudit().catch(()=>undefined); }, []);
  useEffect(() => {
    if (action) window.requestAnimationFrame(()=>operationPanel.current?.focus());
  }, [action]);
  async function refreshInventory() {
    setSyncingInventory(true);
    setInventoryMessage("");
    try {
      const result = await api<{synchronized:number}>("/connections/aws/sync", { method: "POST" });
      const records = await api<Machine[]>("/inventory/servers");
      const awsRecords = records.filter((item) => item.vm_type === "aws" && item.enabled !== false && item.status !== "terminated");
      setInventory(awsRecords);
      setInventoryMessage(result.synchronized ? `${result.synchronized} AWS resource(s) synchronized.` : "Connection succeeded, but no EC2 instances were found in the configured region.");
    } catch (error) { setInventoryMessage((error as Error).message); }
    finally { setSyncingInventory(false); }
  }
  const instanceActions = [
    "start_instance",
    "stop_instance",
    "reboot_instance",
    "terminate_instance",
    "resize_instance",
    "create_snapshot",
    "extend_volume",
    "detach_secondary_nic",
  ];
  const identifier = instanceActions.includes(action) ? target : volume;
  useEffect(() => {
    if (!busy) return;
    setElapsedSeconds(0);
    const started = Date.now();
    const timer = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);
  async function verifyInstanceState(instanceId: string, operation: string) {
    const desired: Record<string, string> = { start_instance: "running", stop_instance: "stopped", terminate_instance: "terminated" };
    const finalState = desired[operation];
    if (!finalState) return "accepted";
    for (let attempt = 0; attempt < 90; attempt += 1) {
      setProgressStage(attempt ? 3 : 2);
      const state = await api<{ status: string }>(`/operations/aws/instances/${encodeURIComponent(instanceId)}/status`);
      setResult(`In progress · ${state.status}`);
      if (state.status === finalState || (finalState === "terminated" && state.status === "not-found")) return finalState;
      await new Promise((resolve) => window.setTimeout(resolve, 3000));
    }
    throw new Error("AWS accepted the operation, but final-state verification timed out. Check the EC2 console.");
  }
  async function execute(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setOperationStarted(true);
    setProgressStage(0);
    setResult("");
    try {
      const payload: Record<string, unknown> = {
        action,
        identifier,
        password: confirmation,
      };
      if (action === "resize_instance") payload.instance_type = instanceType;
      if (
        ["create_snapshot", "extend_volume", "delete_volume"].includes(action)
      )
        payload.volume_id = volume;
      if (action === "extend_volume") payload.size_gib = size;
      if (action === "delete_snapshot") payload.snapshot_id = volume;
      const response = await api<Record<string, unknown>>(
        "/operations/aws/execute",
        { method: "POST", body: JSON.stringify(payload) },
      );
      setProgressStage(1);
      setResult(
        `Accepted · ${String(response.after_status || response.message || "success")}`,
      );
      const finalState = await verifyInstanceState(identifier, action);
      if (finalState !== "accepted") {
        setProgressStage(4);
        setResult(`Completed and verified · ${finalState}`);
      }
      await api("/connections/aws/sync", { method: "POST" });
      const updatedRecords = await api<Machine[]>("/inventory/servers");
      setInventory(updatedRecords.filter((item) => item.vm_type === "aws" && item.enabled !== false && item.status !== "terminated"));
      await loadAudit().catch(()=>undefined);
      setInventoryMessage(`${actionLabel[action] || action.replaceAll("_"," ")} completed for ${selected?.server_name || identifier}.`);
      setOperationStarted(false);
      setAction("");
    } catch (e) {
      const message=(e as Error).message;
      setResult(message.includes("502")?"Operation API is temporarily unavailable (502). Please retry after the deployment service is ready.":message);
    } finally {
      setBusy(false);
    }
  }
  const selected = inventory.find((x) => x.aws_instance_id === target);
  const optionOs = (server: Machine) => {
    const os = `${server.os_type || ""} ${server.os_version || ""}`.toLowerCase();
    return os.includes("windows") ? "Windows" : os.includes("linux") ? "Linux" : "OS unknown";
  };
  const chooseOperation = (operation: string, instanceId?: string) => {
    setAction(operation);
    if (instanceId) setTarget(instanceId);
    setConfirmation("");
    setResult("");
    setOperationStarted(false);
    setShowLiveTrail(false);
  };
  const actionLabel: Record<string, string> = {
    start_instance: "Start VM", stop_instance: "Stop VM", reboot_instance: "Reboot VM",
    resize_instance: "Resize VM", create_snapshot: "Create snapshot", terminate_instance: "Terminate VM",
    detach_secondary_nic: "Detach secondary NIC",
    extend_volume: "Extend EBS volume", delete_volume: "Delete EBS volume", delete_snapshot: "Delete snapshot",
  };
  const runningCount = inventory.filter((server) => String(server.status).toLowerCase() === "running").length;
  const stoppedCount = inventory.filter((server) => String(server.status).toLowerCase() === "stopped").length;
  const visibleInstances = inventory.filter((server) => instanceFilter === "all" || String(server.status).toLowerCase() === instanceFilter);
  const singleSelection = selectedTargets.length === 1 ? inventory.find((server)=>server.aws_instance_id===selectedTargets[0]) : undefined;
  const selectInstance = (instanceId: string, checked: boolean) => {
    setSelectedTargets((current)=>checked ? Array.from(new Set([...current,instanceId])) : current.filter((id)=>id!==instanceId));
    if (checked) setTarget(instanceId); else if (target===instanceId) setTarget("");
    setAction(""); setConfirmation("");
  };
  const auditRows = (audit?.events || []).map((event)=>({
    time:event["Time"] || "—", action:String(event["Action"] || "—").replaceAll("_"," "),
    target:event["Target"] || event["Instance ID"] || event["Volume ID"] || event["Snapshot ID"] || "—",
    status:event["Status"] || "—", requester:event["Requester"] || "—", approver:event["Approver"] || "—",
    state_change:`${String(event["Before"] || "—")} → ${String(event["After"] || "—")}`,
    request_id:event["Request ID"] || event["AWS Request ID"] || "—",
  }));
  return (
    <>
      <section className="operation-page-lead"><div className="operation-lead-icon"><FaAws /></div><div><span>AMAZON WEB SERVICES</span><h2>Guarded AWS operations</h2><p>Preview, approve, execute and verify infrastructure changes from one controlled workspace.</p></div><div className="aws-lead-actions"><div className="operation-lead-state"><i />{inventory.length} managed resources</div><button onClick={refreshInventory} disabled={syncingInventory}><RefreshCw className={syncingInventory?"spin":""}/>{syncingInventory?"Synchronizing…":"Refresh inventory"}</button><button onClick={() => { sessionStorage.setItem("opsagent-chat-draft", "Provision a new AWS EC2 virtual machine."); onNavigate?.("OpsAgent chat"); }}><Sparkles /> Create new VM with agent</button></div></section>
      {inventoryMessage&&<div className={`aws-inventory-message ${inventory.length?"success":"attention"}`}>{inventory.length?<CheckCircle2/>:<AlertTriangle/>}<span>{inventoryMessage}{!inventory.length&&" Check that the selected region contains EC2 instances and the IAM policy allows ec2:DescribeInstances."}</span></div>}
      <section className="aws-overview">
        <article className="aws-command">
          <div className="panel-title">
            <div>
              <p className="eyebrow">LIVE EC2 INVENTORY</p>
              <h3>Virtual machines</h3>
            </div>
            <div className="aws-state-summary"><span><i className="running"/>{runningCount} Running</span><span><i className="stopped"/>{stoppedCount} Stopped</span><span>{inventory.length} Total</span><span>10 operations available</span></div>
          </div>
          {inventory.length ? <div className="aws-instance-console">
            <div className="aws-table-toolbar"><div><b>Instances ({visibleInstances.length})</b><span>{selectedTargets.length===0?"Select an instance to manage":selectedTargets.length===1?`${singleSelection?.server_name || "1 instance"} selected`:`${selectedTargets.length} selected · choose one instance to run a guarded action`}</span></div><div className="aws-toolbar-actions"><button className="start" disabled={!singleSelection||String(singleSelection.status).toLowerCase()!=="stopped"} onClick={()=>chooseOperation("start_instance",selectedTargets[0])}>Start</button><button className="stop" disabled={!singleSelection||String(singleSelection.status).toLowerCase()!=="running"} onClick={()=>chooseOperation("stop_instance",selectedTargets[0])}>Stop</button><button disabled={!singleSelection||String(singleSelection.status).toLowerCase()!=="running"} onClick={()=>chooseOperation("reboot_instance",selectedTargets[0])}>Reboot</button><button disabled={!singleSelection} onClick={()=>chooseOperation("resize_instance",selectedTargets[0])}>Resize</button><button disabled={!singleSelection} onClick={()=>chooseOperation("create_snapshot",selectedTargets[0])}>Snapshot</button><button disabled={!singleSelection} onClick={()=>chooseOperation("detach_secondary_nic",selectedTargets[0])}>Detach NIC</button><button className="danger" disabled={!singleSelection} onClick={()=>chooseOperation("terminate_instance",selectedTargets[0])}>Terminate</button><i className="toolbar-divider"/><button onClick={()=>chooseOperation("extend_volume")}>Extend volume</button><button onClick={()=>chooseOperation("delete_volume")}>Delete volume</button><button onClick={()=>chooseOperation("delete_snapshot")}>Delete snapshot</button></div></div>
            <div className="aws-instance-filters"><span>Instance state</span>{(["all","running","stopped"] as const).map((filter)=><button className={instanceFilter===filter?"active":""} onClick={()=>setInstanceFilter(filter)} key={filter}>{filter==="all"?`All (${inventory.length})`:filter==="running"?`Running (${runningCount})`:`Stopped (${stoppedCount})`}</button>)}</div>
            <div className="aws-instance-table-wrap"><table className="aws-instance-table"><thead><tr><th><input type="checkbox" checked={visibleInstances.length>0&&visibleInstances.every((server)=>selectedTargets.includes(server.aws_instance_id))} onChange={(event)=>{const ids=visibleInstances.map((server)=>server.aws_instance_id);setSelectedTargets(event.target.checked?Array.from(new Set([...selectedTargets,...ids])):selectedTargets.filter((id)=>!ids.includes(id)));setTarget("");setAction("");setConfirmation("");}} aria-label="Select all visible instances"/></th><th>Name</th><th>Instance ID</th><th>Instance state</th><th>Instance type</th><th>Status check</th><th>Availability Zone</th><th>Public IPv4 DNS</th><th>Public IPv4</th><th>Elastic IP</th><th>Private IPv4</th><th>Monitoring</th><th>Environment</th></tr></thead><tbody>{visibleInstances.map((server)=>{const state=String(server.status||"unknown").toLowerCase();return <tr className={selectedTargets.includes(server.aws_instance_id)?"selected":""} key={server.aws_instance_id} onClick={()=>selectInstance(server.aws_instance_id,!selectedTargets.includes(server.aws_instance_id))}><td><input type="checkbox" checked={selectedTargets.includes(server.aws_instance_id)} onChange={(event)=>selectInstance(server.aws_instance_id,event.target.checked)} onClick={(event)=>event.stopPropagation()} aria-label={`Select ${server.server_name}`}/></td><td><span className="aws-table-name"><i className={optionOs(server).toLowerCase()}>{optionOs(server).toLowerCase()==="windows"?<FaWindows/>:<SiLinux/>}</i><b>{server.server_name||"Unnamed VM"}</b></span></td><td><code>{server.aws_instance_id}</code></td><td><span className={`vm-power-state ${state}`}><i/>{state}</span></td><td>{server.instance_type||"—"}</td><td>—</td><td>{server.availability_zone||"—"}</td><td title={server.public_dns_name||""}>{server.public_dns_name||"—"}</td><td>{server.public_ip_address||"—"}</td><td>—</td><td>{server.private_ip_address||server.ip_address||"—"}</td><td>{server.monitoring_service||"disabled"}</td><td>{server.environment||"—"}</td></tr>})}</tbody></table></div>
          </div>:<div className="aws-vm-empty"><Server/><h3>No EC2 virtual machines found</h3><p>Refresh inventory or verify the connected AWS account and region.</p></div>}
          {action && <div className="aws-operation-backdrop" role="presentation" onMouseDown={()=>{if(!busy){setAction("");setOperationStarted(false);}}}><section className="aws-operation-review" ref={operationPanel} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Confirm AWS operation" onMouseDown={(event)=>event.stopPropagation()}>
            <header><div><span>{operationStarted?"OPERATION STATUS":"CONFIRM OPERATION"}</span><h3>{actionLabel[action] || action.replaceAll("_"," ")}</h3></div><button disabled={busy} onClick={()=>{setAction("");setConfirmation("");setOperationStarted(false);}} aria-label="Close operation"><X/></button></header>
          <form className="operation-form" onSubmit={execute}>
            {!operationStarted?<>
            <dl className="aws-confirm-summary"><div><dt>Server</dt><dd>{selected?.server_name || identifier || "AWS resource"}</dd></div><div><dt>Operation</dt><dd>{actionLabel[action] || action.replaceAll("_"," ")}</dd></div></dl>
            <div className="form-grid">
              {action === "resize_instance" && (
                <label>
                  New instance type
                  <input
                    value={instanceType}
                    onChange={(e) => setInstanceType(e.target.value)}
                  />
                </label>
              )}
              {[
                "create_snapshot",
                "extend_volume",
                "delete_volume",
                "delete_snapshot",
              ].includes(action) && (
                <label>
                  {action === "delete_snapshot" ? "Snapshot ID" : "Volume ID"}
                  <input
                    value={volume}
                    onChange={(e) => setVolume(e.target.value)}
                    placeholder={
                      action === "delete_snapshot" ? "snap-…" : "vol-…"
                    }
                  />
                </label>
              )}
              {action === "extend_volume" && (
                <label>
                  New size (GiB)
                  <input
                    type="number"
                    value={size}
                    onChange={(e) => setSize(Number(e.target.value))}
                  />
                </label>
              )}
            </div>
            <div className="aws-confirm-fields"><label>Username<input value={user.username} readOnly /></label><label>Password<input type="password" value={confirmation} onChange={(e) => setConfirmation(e.target.value)} placeholder="Enter password" autoComplete="current-password" autoFocus /></label></div>
            <button
              className="execute"
              disabled={!identifier || !confirmation}
            >
              Confirm and run
            </button>
            </>:<><section className={`aws-simple-progress ${!busy&&result?"failed":""}`} aria-live="polite"><header><div>{!busy&&result?<AlertTriangle/>:progressStage>=4?<CheckCircle2/>:<RefreshCw className="spin"/>}<span><strong>{!busy&&result?"Operation failed":progressStage>=4?"Operation completed":"Operation in progress"}</strong><small>{selected?.server_name || identifier} · {elapsedSeconds}s</small></span></div><b>{Math.min(100,(progressStage+1)*20)}%</b></header><div className="aws-simple-track"><i style={{width:`${Math.min(100,(progressStage+1)*20)}%`}}/></div><ol>{["Verified","Submitted","Changing state","Checking state","Completed"].map((label,index)=><li className={!busy&&result&&index===progressStage?"failed":index<progressStage||progressStage>=4?"complete":index===progressStage?"active":""} key={label}><i>{index<progressStage||progressStage>=4?<CheckCircle2/>:index+1}</i><span>{label}</span></li>)}</ol><footer>{!busy&&result?result:progressStage>=4?"AWS state verified successfully.":"OpsAgent is waiting for AWS to report the final state."}</footer><button type="button" className="aws-live-trail-toggle" onClick={()=>setShowLiveTrail((value)=>!value)}>{showLiveTrail?"Hide live trail":"Show live trail"}<ChevronDown className={showLiveTrail?"open":""}/></button>{showLiveTrail&&<pre className="aws-live-trail"><code><span>00:00</span> Verify user identity and RBAC{"\n"}<span>00:01</span> Submit {action} for {identifier}{progressStage>=1?"\n00:02 AWS accepted the request":""}{progressStage>=2?"\n00:03 Resource state transition detected":""}{progressStage>=3?"\n00:04 Polling EC2 instance state":""}{progressStage>=4?"\n00:05 Final AWS state verified":""}{!busy&&result?`\nERROR ${result}`:""}</code></pre>}</section>{!busy&&result&&<div className="aws-progress-actions"><button type="button" onClick={()=>{setAction("");setOperationStarted(false);}}>Close</button><button type="button" onClick={()=>{setOperationStarted(false);setResult("");setShowLiveTrail(false);}}>Try again</button></div>}</>}
          </form>
          </section></div>}
        </article>
      </section>
      {audit && <SimpleTable rows={auditRows} title="Logs" />}
    </>
  );
}

function Usage() {
  const [summary, setSummary] = useState<Record<string, number> | null>(null);
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [breakdown, setBreakdown] = useState<Record<string, unknown>[]>([]);
  const [hours, setHours] = useState(720);
  const [costSection, setCostSection] = useState("All sections");
  const [chartMetric, setChartMetric] = useState<"cost" | "tokens" | "calls">("cost");
  const [currency, setCurrency] = useState("USD");
  const defaultRates: Record<string, number> = { USD: 1, INR: 83, EUR: .92, GBP: .79 };
  const [rate, setRate] = useState(1);
  const [error, setError] = useState("");
  useEffect(() => {
    setError("");
    Promise.all([
      api<Record<string, number>>(`/usage/summary?hours=${hours}`),
      api<Record<string, unknown>[]>(`/usage/events?hours=${hours}`),
      api<Record<string, unknown>[]>(`/usage/breakdown?hours=${hours}`),
    ]).then(([a, b, c]) => {
      setSummary(a);
      setEvents(b);
      setBreakdown(c);
    }).catch((failure) => setError((failure as Error).message));
  }, [hours]);
  if (error) return <section className="product-page"><div className="connector-error"><AlertTriangle/><div><strong>AI usage data is unavailable</strong><p>{error}</p></div></div></section>;
  if (!summary) return <div className="skeleton">Loading usage…</div>;
  const symbols: Record<string, string> = { USD: "$", INR: "₹", EUR: "€", GBP: "£" };
  const convertedCost = Number(summary.cost_usd || 0) * rate;
  const chartEvents = [...events].slice(0, 14).reverse();
  const maxCost = Math.max(...chartEvents.map((event) => Number(event["Estimated cost USD"] || 0)), .000001);
  const formatMoney = (value: number) => `${symbols[currency]}${value.toLocaleString(undefined, { minimumFractionDigits: value < 1 ? 4 : 2, maximumFractionDigits: value < 1 ? 6 : 2 })}`;
  const sectionForActivity = (activity: unknown) => {
    const value = String(activity || "").toLowerCase();
    if (["infrastructure_chat", "investigation_chat", "historical_chat_unmetered", "local_chat"].includes(value)) return "OpsAgent Chat";
    if (value === "incident_agent") return "Monitoring Agent";
    if (value.startsWith("slack")) return "Slack alerts";
    if (value.startsWith("gmail") || value.startsWith("email")) return "Gmail alerts";
    if (value.startsWith("aws_")) return "AWS operations";
    if (value.startsWith("windows_") || value.startsWith("ssm_windows")) return "Windows operations";
    if (value.startsWith("linux_") || value.startsWith("ssm_linux")) return "Linux operations";
    if (value.startsWith("agent_")) return "Agent orchestration";
    return "Other";
  };
  const visualEvents = events.filter((event) => costSection === "All sections" || sectionForActivity(event.Activity) === costSection);
  const trendMap = new Map<string, number>();
  visualEvents.forEach((event) => {
    const key = String(event.Time || "").slice(0, 10);
    const value = chartMetric === "cost" ? Number(event["Estimated cost USD"] || 0) * rate : chartMetric === "tokens" ? Number(event["Total tokens"] || 0) : String(event.Model) === "local-rules" ? 0 : 1;
    trendMap.set(key, (trendMap.get(key) || 0) + value);
  });
  const trendPoints = [...trendMap.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-30);
  const trendMax = Math.max(...trendPoints.map(([, value]) => value), 0.000001);
  const polyline = trendPoints.map(([, value], index) => `${trendPoints.length === 1 ? 50 : index / (trendPoints.length - 1) * 100},${94 - value / trendMax * 82}`).join(" ");
  const pieColors = ["#4965e8", "#17a673", "#ef9b35", "#8c62d9", "#e05260", "#2694d1", "#657487", "#d66bb0", "#9a7b35"];
  const pieRows = breakdown.filter((item) => Number(item.cost_usd || 0) > 0);
  let pieCursor = 0;
  const pieGradient = pieRows.length ? `conic-gradient(${pieRows.map((item, index) => { const start = pieCursor; pieCursor += Number(item.share_percent || 0); return `${pieColors[index % pieColors.length]} ${start}% ${pieCursor}%`; }).join(",")})` : "#e7ebf1";
  const rangeLabel = hours === 24 ? "Last 24 hours" : hours === 168 ? "Last 7 days" : hours === 720 ? "Last 30 days" : "Last 90 days";
  return (
    <section className="usage-page product-page">
      <div className="page-lead"><div><span className="badge">AI FINOPS</span><h2>AI usage and cost intelligence</h2><p>Understand model consumption, compare activity and control estimated spend across your organization.</p></div><div className="currency-control"><label>Display currency<select value={currency} onChange={(e) => { const next=e.target.value; setCurrency(next); setRate(defaultRates[next]); }}><option>USD</option><option>INR</option><option>EUR</option><option>GBP</option></select></label><label>Rate per USD<input type="number" step="0.01" value={rate} onChange={(e) => setRate(Number(e.target.value) || 0)} /></label><small>Editable display conversion—not a billing exchange rate.</small></div></div>
      <section className="finops-controls"><div><label>Time range<select value={hours} onChange={(event) => setHours(Number(event.target.value))}><option value={24}>Last 24 hours</option><option value={168}>Last 7 days</option><option value={720}>Last 30 days</option><option value={2160}>Last 90 days</option></select></label><label>Product section<select value={costSection} onChange={(event) => setCostSection(event.target.value)}><option>All sections</option>{breakdown.map((item) => <option key={String(item.section)}>{String(item.section)}</option>)}</select></label><label>Chart metric<select value={chartMetric} onChange={(event) => setChartMetric(event.target.value as "cost" | "tokens" | "calls")}><option value="cost">Estimated cost</option><option value="tokens">Tokens</option><option value="calls">Model calls</option></select></label></div><span><RefreshCw/> Charts update automatically</span></section>
      <section className="usage-kpis">
        {[
          ["Interactions", summary.interactions],
          ["Model calls", summary.calls],
          ["Input tokens", summary.input_tokens],
          ["Output tokens", summary.output_tokens],
          ["Estimated cost", formatMoney(convertedCost)],
        ].map(([x, y]) => (
          <article key={String(x)}>
            <span>{x}</span>
            <strong>{y}</strong>
            <small>{rangeLabel}</small>
          </article>
        ))}
      </section>
      <section className="finops-chart-grid"><article className="finops-trend"><header><div><span>TREND ANALYSIS</span><h3>{costSection} · {chartMetric === "cost" ? "estimated cost" : chartMetric}</h3></div><b>{rangeLabel}</b></header>{trendPoints.length ? <><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Usage trend"><defs><linearGradient id="finopsArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#4965e8" stopOpacity=".32"/><stop offset="1" stopColor="#4965e8" stopOpacity=".02"/></linearGradient></defs><polygon points={`0,100 ${polyline} 100,100`} fill="url(#finopsArea)"/><polyline points={polyline} fill="none" stroke="#4965e8" strokeWidth="2" vectorEffect="non-scaling-stroke"/></svg><div className="trend-labels"><span>{trendPoints[0]?.[0]}</span><strong>Peak {chartMetric === "cost" ? formatMoney(trendMax) : Math.round(trendMax).toLocaleString()}</strong><span>{trendPoints.at(-1)?.[0]}</span></div></> : <div className="finops-empty">No metered activity for this selection.</div>}</article><article className="finops-pie"><header><span>COST DISTRIBUTION</span><h3>Share by section</h3></header><div className="pie-layout"><div className="cost-pie" style={{background:pieGradient}}><i><strong>{formatMoney(convertedCost)}</strong><span>Total</span></i></div><div className="pie-legend">{pieRows.length ? pieRows.map((item,index)=><div key={String(item.section)}><i style={{background:pieColors[index%pieColors.length]}}/><span>{String(item.section)}</span><b>{Number(item.share_percent||0).toFixed(1)}%</b></div>):<p>No metered cost</p>}</div></div></article></section>
      <section className="api-cost-ledger">
        <header><div><span>SECTION ALLOCATION</span><h3>AI API cost by product area</h3><p>Every dollar is assigned to the workflow that initiated the model call. Direct AWS and SSM operations show zero unless they invoke AI.</p></div><strong>{formatMoney(convertedCost)}<small>{rangeLabel} estimated total</small></strong></header>
        <div className="api-cost-columns"><span>Section</span><span>Type</span><span>Interactions</span><span>Model calls</span><span>Tokens</span><span>Cost share</span><span>Estimated cost</span></div>
        {breakdown.map((item) => { const usd = Number(item.cost_usd || 0); const share = Number(item.share_percent || 0); return <div className="api-cost-row" key={String(item.section)}><div><b>{String(item.section)}</b><small>{String(item.cost_note)}</small></div><span>{String(item.category)}</span><strong>{Number(item.interactions || 0).toLocaleString()}</strong><strong>{Number(item.model_calls || 0).toLocaleString()}</strong><strong>{Number(item.total_tokens || 0).toLocaleString()}</strong><div className="cost-share"><i><b style={{width:`${share}%`}} /></i><span>{share.toFixed(2)}%</span></div><strong>{formatMoney(usd * rate)}</strong></div> })}
        <footer><ShieldCheck/><span><b>Cost boundary:</b> This dashboard estimates OpenAI model usage only. AWS EC2/SSM, Slack and Gmail connector charges are not invented; provider billing remains in each provider’s billing console.</span></footer>
      </section>
      <section className="usage-visuals"><article className="usage-chart"><div className="intel-title"><div><span>COST TREND</span><h3>Estimated cost by recent activity</h3></div><b>{formatMoney(convertedCost)} total</b></div><div className="cost-bars">{chartEvents.length ? chartEvents.map((event, index) => { const usd=Number(event["Estimated cost USD"] || 0); return <div key={index}><i style={{height:`${Math.max(3,usd/maxCost*100)}%`}} title={`${String(event.Activity || "Activity")}: ${formatMoney(usd*rate)}`} /><span>{index+1}</span></div> }) : <div className="chart-no-data">No metered calls yet</div>}</div></article><article className="usage-breakdown"><span>EFFICIENCY</span><h3>Token distribution</h3><div className="token-total"><strong>{Number(summary.total_tokens || 0).toLocaleString()}</strong><small>Total tokens</small></div><div className="token-split"><i style={{width:`${summary.total_tokens ? summary.input_tokens/summary.total_tokens*100 : 0}%`}} /></div><p><span>Input {Number(summary.input_tokens || 0).toLocaleString()}</span><span>Output {Number(summary.output_tokens || 0).toLocaleString()}</span></p></article></section>
      <SimpleTable rows={events.map((event) => ({...event, [`Estimated cost ${currency}`]: formatMoney(Number(event["Estimated cost USD"] || 0)*rate)}))} title="AI usage events" />
    </section>
  );
}

function Account({ user }: { user: User }) {
  const [users, setUsers] = useState<Record<string, unknown>[]>([]);
  const [audit, setAudit] = useState<Record<string, unknown>[]>([]);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [message, setMessage] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [inviteRole, setInviteRole] = useState("Viewer");
  const [mfaEnabled, setMfaEnabled] = useState(false);
  const [mfaSetup, setMfaSetup] = useState<{secret:string;otpauth_uri:string}|null>(null);
  const [mfaCode, setMfaCode] = useState("");
  async function refreshAccess() {
    const [accounts, events] = await Promise.all([
      api<Record<string, unknown>[]>("/iam/members"),
      api<Record<string, unknown>[]>("/access/audit"),
    ]);
    setUsers(accounts);
    setAudit(events);
  }
  useEffect(() => {
    if (["Owner", "Admin"].includes(user.organization_role || ""))
      refreshAccess();
  }, [user.organization_role]);
  useEffect(()=>{ api<{enabled:boolean}>("/auth/mfa/status").then((value)=>setMfaEnabled(value.enabled)); },[]);
  async function startMfa() { try { setMfaSetup(await api<{secret:string;otpauth_uri:string}>("/auth/mfa/setup",{method:"POST"})); setMessage(""); } catch(error){setMessage((error as Error).message);} }
  async function enableMfa(e:FormEvent){e.preventDefault();try{await api("/auth/mfa/enable",{method:"POST",body:JSON.stringify({code:mfaCode})});setMfaEnabled(true);setMfaSetup(null);setMfaCode("");setMessage("Authenticator MFA enabled successfully");}catch(error){setMessage((error as Error).message);}}
  async function updateAccess(
    username: string,
    role: string,
    enabled: boolean,
  ) {
    setMessage(`Updating ${username}…`);
    try {
      await api(`/iam/members/${encodeURIComponent(username)}`, {
        method: "PATCH",
        body: JSON.stringify({
          role,
          status: enabled ? "active" : "suspended",
        }),
      });
      await refreshAccess();
      setMessage(`${username} updated to ${role}`);
    } catch (error) {
      setMessage((error as Error).message);
    }
  }
  async function createAccount(e: FormEvent) {
    e.preventDefault();
    try {
      await api("/iam/members", {
        method: "POST",
        body: JSON.stringify({ username:newUsername, display_name:newDisplayName, password:newPassword, role:inviteRole }),
      });
      setMessage(`Account ${newUsername} created successfully. The user can sign in now.`);
      setNewUsername("");
      setNewDisplayName("");
      setNewPassword("");
      await refreshAccess();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }
  async function password(e: FormEvent) {
    e.preventDefault();
    try {
      await api("/access/password", {
        method: "POST",
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      setMessage("Password updated successfully");
    } catch (e) {
      setMessage((e as Error).message);
    }
  }
  return (
    <>
      <section className="profile-card">
        <div className="avatar large">
          {user.display_name.slice(0, 2).toUpperCase()}
        </div>
        <div>
          <h2>{user.display_name}</h2>
          <p>
            {user.username}
          </p>
          <small>{user.name || "Current organization"}</small>
        </div>
        <span className="status running">{displayRole(user.organization_role || user.role)}</span>
      </section>
      <section className="grid">
        <article className="panel account-overview">
          <span className="eyebrow">IDENTITY & ACCESS</span>
          <h3>Organization access</h3>
          <strong>{displayRole(user.organization_role || user.role)}</strong>
          <p className="muted">Your effective role for this organization. Cloud permissions are evaluated separately for every operation.</p>
        </article>
        <details className="panel account-security">
          <summary><div><span className="eyebrow">AUTHENTICATION</span><h3>Local password</h3><p className="muted">Update credentials only for a local OpsAgent account.</p></div><ChevronDown /></summary>
          <form className="operation-form" onSubmit={password}>
            <label>
              Current password
              <input
                type="password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
              />
            </label>
            <label>
              New password
              <input
                type="password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
              />
            </label>
            <button>Update password</button>
            {message && <p className="notice">{message}</p>}
          </form>
        </details>
        <article className="panel mfa-panel"><div className="mfa-heading"><ShieldCheck/><div><span className="eyebrow">STEP-UP SECURITY</span><h3>Authenticator MFA</h3><p className="muted">Required for permanent infrastructure termination.</p></div><b className={mfaEnabled?"enabled":"required"}>{mfaEnabled?"Enabled":"Setup required"}</b></div>{!mfaEnabled&&!mfaSetup&&<button onClick={startMfa}>Set up authenticator</button>}{mfaSetup&&<form onSubmit={enableMfa}><p>Add an account manually in Microsoft Authenticator, Google Authenticator or 1Password.</p><label>Setup key<code>{mfaSetup.secret}</code></label><a href={mfaSetup.otpauth_uri}>Open authenticator app</a><label>Verify 6-digit code<input inputMode="numeric" maxLength={6} value={mfaCode} onChange={(e)=>setMfaCode(e.target.value.replace(/\D/g,"").slice(0,6))}/></label><button disabled={mfaCode.length!==6}>Verify and enable MFA</button></form>}</article>
      </section>
      {["Owner", "Admin"].includes(user.organization_role || "") && (
        <>
          <section className="panel invitation-panel">
            <div>
              <h3>Create organization account</h3>
              <p className="muted">
                Create a local account that can sign in immediately.
              </p>
            </div>
            <form onSubmit={createAccount}>
              <input
                required
                minLength={3}
                maxLength={64}
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value.toLowerCase().replace(/[^a-z0-9._-]/g,""))}
                placeholder="Username"
              />
              <input
                required
                maxLength={120}
                value={newDisplayName}
                onChange={(e) => setNewDisplayName(e.target.value)}
                placeholder="Display name"
              />
              <input
                type="password"
                required
                minLength={12}
                maxLength={256}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Temporary password (12+ characters)"
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
              >
                <option>Viewer</option>
                <option>Operator</option>
                <option>Approver</option>
                <option>Auditor</option>
                <option>Admin</option>
              </select>
              <button>Create account</button>
            </form>
          </section>
          <h2 className="section-title">Organization users</h2>
          <section className="panel inventory access-management">
            <table>
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Last login</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {users.map((account) => {
                  const username = String(account["username"]);
                  const currentRole = String(account["role"]);
                  const enabled = account["status"] === "active";
                  return (
                    <AccessRow
                      key={username}
                      username={username}
                      displayName={String(account["display_name"])}
                      currentRole={currentRole}
                      enabled={enabled}
                      lastLogin={String(account["last_login_at"] || "Never")}
                      onSave={updateAccess}
                    />
                  );
                })}
              </tbody>
            </table>
          </section>
          {message && <p className="notice access-notice">{message}</p>}
          <h2 className="section-title">Access audit</h2>
          <SimpleTable rows={audit} />
        </>
      )}
    </>
  );
}

function AccessRow({
  username,
  displayName,
  currentRole,
  enabled,
  lastLogin,
  onSave,
}: {
  username: string;
  displayName: string;
  currentRole: string;
  enabled: boolean;
  lastLogin: string;
  onSave: (username: string, role: string, enabled: boolean) => void;
}) {
  const [role, setRole] = useState(currentRole);
  const [active, setActive] = useState(enabled);
  return (
    <tr>
      <td>
        <strong>{displayName}</strong>
        <small>{username}</small>
      </td>
      <td>
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option>Viewer</option>
          <option>Operator</option>
          <option>Approver</option>
          <option>Auditor</option>
          <option>Admin</option>
          <option value="Owner">Root</option>
        </select>
      </td>
      <td>
        <label className="access-switch">
          <input
            type="checkbox"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
          />
          {active ? "Enabled" : "Disabled"}
        </label>
      </td>
      <td>{lastLogin}</td>
      <td>
        <button
          onClick={() => onSave(username, role, active)}
          disabled={role === currentRole && active === enabled}
        >
          Save access
        </button>
      </td>
    </tr>
  );
}

type SccmInventory = {
  success: boolean;
  mode: string;
  instance_id?: string;
  command_id?: string;
  collected_at?: string;
  site_code?: string;
  provider?: string;
  summary: Record<string, number>;
  devices: Record<string, unknown>[];
  collections: Record<string, unknown>[];
  deployments: Record<string, unknown>[];
  update_groups: Record<string, unknown>[];
};

type PatchCycle = Record<string, unknown> & {
  cycle_id: string; name: string; status: string; current_stage: number;
  approval_status: string; stage: { index: number; code: string; title: string; description: string };
  stages?: { index: number; code: string; title: string; description: string; state: string }[];
};

function SccmPatchPipeline({ inventory }: { inventory: SccmInventory }) {
  const collectionNames = inventory.collections.map((row) => String(row.Name || "")).filter(Boolean);
  const [cycles, setCycles] = useState<PatchCycle[]>([]);
  const [selected, setSelected] = useState<PatchCycle | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ name: "", release_date: "", test_date: "", production_date: "", deadline_date: "", kb_ids: "", software_update_group: "", deployment_package: "", test_collection: collectionNames[0] || "", pilot_collection: "", production_collection: collectionNames[0] || "", change_system: "ServiceNow", change_id: "", stakeholder_emails: "", application_emails: "" });
  const loadCycles = () => api<PatchCycle[]>("/sccm/patch-cycles").then(setCycles).catch((failure) => setError(failure.message));
  useEffect(() => { loadCycles(); }, []);
  const update = (name: string, value: string) => setForm((current) => ({ ...current, [name]: value }));
  const open = async (cycleId: string) => { setError(""); try { setSelected(await api<PatchCycle>(`/sccm/patch-cycles/${cycleId}`)); } catch (failure) { setError((failure as Error).message); } };
  const create = async (event: FormEvent) => { event.preventDefault(); setBusy(true); setError(""); try { const payload = { ...form, kb_ids: form.kb_ids.split(/[,\s]+/).filter(Boolean), stakeholder_emails: form.stakeholder_emails.split(/[,;\s]+/).filter(Boolean), application_emails: form.application_emails.split(/[,;\s]+/).filter(Boolean), test_date: new Date(form.test_date).toISOString(), production_date: new Date(form.production_date).toISOString(), deadline_date: new Date(form.deadline_date).toISOString() }; const cycle = await api<PatchCycle>("/sccm/patch-cycles", { method: "POST", body: JSON.stringify(payload) }); setSelected(cycle); setCreating(false); await loadCycles(); } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); } };
  const act = async (action: "approve" | "advance") => { if (!selected) return; setBusy(true); setError(""); try { const cycle = await api<PatchCycle>(`/sccm/patch-cycles/${selected.cycle_id}/${action}`, { method: "POST", body: action === "advance" ? JSON.stringify({ evidence: {} }) : undefined }); setSelected(cycle); await loadCycles(); } catch (failure) { setError((failure as Error).message); } finally { setBusy(false); } };
  return <section className="patch-pipeline"><header><div><span>AUTOMATED PATCH GOVERNANCE</span><h3>Monthly SCCM patch pipeline</h3><p>Plan, test, approve, deploy, verify and close every Microsoft patch cycle.</p></div><button onClick={() => setCreating((value) => !value)}>{creating ? "Cancel" : "+ New patch cycle"}</button></header>
    {error && <div className="connector-error"><AlertTriangle/><div><strong>Pipeline action blocked</strong><p>{error}</p></div></div>}
    {creating && <form className="patch-cycle-form" onSubmit={create}><label>Cycle name<input required value={form.name} onChange={(e)=>update("name",e.target.value)} placeholder="September 2026 Windows patches"/></label><label>Microsoft release date<input required type="date" value={form.release_date} onChange={(e)=>update("release_date",e.target.value)}/></label><label>Test deployment<input required type="datetime-local" value={form.test_date} onChange={(e)=>update("test_date",e.target.value)}/></label><label>Production deployment<input required type="datetime-local" value={form.production_date} onChange={(e)=>update("production_date",e.target.value)}/></label><label>Production deadline<input required type="datetime-local" value={form.deadline_date} onChange={(e)=>update("deadline_date",e.target.value)}/></label><label>Microsoft KBs<input value={form.kb_ids} onChange={(e)=>update("kb_ids",e.target.value)} placeholder="KB5065426, KB5065427"/></label><label>Software Update Group<input required value={form.software_update_group} onChange={(e)=>update("software_update_group",e.target.value)} placeholder="SUG-2026-09-Windows"/></label><label>Deployment package<input required value={form.deployment_package} onChange={(e)=>update("deployment_package",e.target.value)} placeholder="PKG-2026-09-Windows"/></label><label>Test collection<select required value={form.test_collection} onChange={(e)=>update("test_collection",e.target.value)}>{collectionNames.map((name)=><option key={name}>{name}</option>)}</select></label><label>Pilot collection<select value={form.pilot_collection} onChange={(e)=>update("pilot_collection",e.target.value)}><option value="">No pilot collection</option>{collectionNames.map((name)=><option key={name}>{name}</option>)}</select></label><label>Production collection<select required value={form.production_collection} onChange={(e)=>update("production_collection",e.target.value)}>{collectionNames.map((name)=><option key={name}>{name}</option>)}</select></label><label>Change system<select value={form.change_system} onChange={(e)=>update("change_system",e.target.value)}><option>ServiceNow</option><option>Jira</option><option>Manual</option></select></label><label>Change ID<input value={form.change_id} onChange={(e)=>update("change_id",e.target.value)} placeholder="CHG0012345"/></label><label>Stakeholder emails<input value={form.stakeholder_emails} onChange={(e)=>update("stakeholder_emails",e.target.value)} placeholder="ops@example.com, owner@example.com"/></label><label>Application validation emails<input value={form.application_emails} onChange={(e)=>update("application_emails",e.target.value)} placeholder="app-team@example.com"/></label><button disabled={busy}>{busy?"Creating…":"Create patch cycle"}</button></form>}
    <div className="patch-cycle-list">{cycles.map((cycle)=><button className={selected?.cycle_id===cycle.cycle_id?"active":""} onClick={()=>open(cycle.cycle_id)} key={cycle.cycle_id}><span>{cycle.name}</span><small>{cycle.cycle_id}</small><b>{cycle.stage?.title}</b><em>{cycle.approval_status}</em></button>)}{!cycles.length&&!creating&&<div className="data-grid-empty"><Workflow/><strong>No patch cycles yet</strong><span>Create the first monthly patch plan.</span></div>}</div>
    {selected && <section className="patch-cycle-detail"><header><div><span>{selected.cycle_id}</span><h3>{selected.name}</h3><p>Current stage: <b>{selected.stage.title}</b> · Approval: <b>{selected.approval_status}</b></p></div><div>{selected.current_stage>=5&&selected.approval_status!=="approved"&&<button className="approve" onClick={()=>act("approve")} disabled={busy}><ShieldCheck/>Approve cycle</button>}<button onClick={()=>act("advance")} disabled={busy||selected.status==="completed"}>{busy?"Working…":selected.status==="completed"?"Cycle complete":"Complete stage & continue"}</button></div></header><div className="patch-stage-track">{selected.stages?.map((stage)=><article className={stage.state} key={stage.code}><i>{stage.state==="complete"?<CheckCircle2/>:stage.index+1}</i><div><span>{stage.title}</span><small>{stage.description}</small></div><b>{stage.state}</b></article>)}</div>{selected.stage.code==="compliance"&&<div className="patch-compliance-callout"><Activity/><div><strong>Live SCCM compliance monitoring</strong><span>Synchronize SCCM to update compliant, in-progress, failed, pending and unknown results for the selected deployment collections.</span></div></div>}</section>}
  </section>;
}

function SccmWorkspace() {
  const [inventory, setInventory] = useState<SccmInventory | null>(null);
  const [audit, setAudit] = useState<Record<string, unknown>[]>([]);
  const [tab, setTab] = useState("Overview");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const load = async (refresh = false) => {
    setBusy(true); setError("");
    try {
      const [nextInventory, nextAudit] = await Promise.all([
        api<SccmInventory>(`/sccm/inventory${refresh ? "?refresh=true" : ""}`),
        api<Record<string, unknown>[]>("/sccm/audit?limit=100"),
      ]);
      setInventory(nextInventory); setAudit(nextAudit);
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  };
  useEffect(() => { load(); }, []);
  const tabs = ["Overview", "Patch pipeline", "Devices", "Collections", "Deployments", "Update groups", "Audit"];
  const rows = tab === "Devices" ? inventory?.devices : tab === "Collections" ? inventory?.collections : tab === "Deployments" ? inventory?.deployments : tab === "Update groups" ? inventory?.update_groups : tab === "Audit" ? audit : [];
  return <section className="sccm-workspace">
    <section className="sccm-lead"><div className="sccm-mark"><FaMicrosoft /></div><div><span>MICROSOFT CONFIGURATION MANAGER</span><h2>Endpoint intelligence and patch operations</h2><p>Live SCCM inventory collected through an approval-controlled AWS Systems Manager connector.</p></div><div className="sccm-connection"><i className={error ? "error" : inventory ? "online" : ""}/><b>{error ? "Attention required" : inventory ? `Site ${inventory.site_code || "connected"}` : "Connecting"}</b><small>{inventory?.instance_id || "OPSAGENT-SCCM01"}</small></div><button onClick={() => load(true)} disabled={busy}><RefreshCw className={busy ? "spin" : ""}/>{busy ? "Synchronizing…" : "Sync SCCM"}</button></section>
    {error && <div className="connector-error"><AlertTriangle/><div><strong>SCCM connector failed</strong><p>{error}</p></div><button onClick={() => load(true)}>Retry</button></div>}
    {inventory && <><section className="sccm-metrics">{[["Managed devices", inventory.summary.devices || 0], ["Active clients", inventory.summary.active_clients || 0], ["Device collections", inventory.summary.collections || 0], ["Deployments", inventory.summary.deployments || 0], ["Update groups", inventory.summary.update_groups || 0]].map(([label,value])=><article key={String(label)}><span>{label}</span><strong>{value}</strong></article>)}</section>
    <section className="sccm-meta"><div><span>Last synchronized</span><b>{inventory.collected_at ? new Date(inventory.collected_at).toLocaleString() : "—"}</b></div><div><span>SMS Provider</span><b>{inventory.provider || "—"}</b></div><div><span>SSM command</span><b>{inventory.command_id || "—"}</b></div><div><ShieldCheck/><span>Read-only inventory · audited through PostgreSQL</span></div></section></>}
    <nav className="sccm-tabs">{tabs.map((item)=><button className={tab===item?"active":""} onClick={()=>setTab(item)} key={item}>{item}</button>)}</nav>
    {busy && !inventory ? <div className="skeleton">Collecting live SCCM inventory…</div> : tab === "Overview" ? <section className="sccm-overview"><article><h3>Connector workflow</h3><ol><li><b>Request</b><span>OpsAgent requests inventory from the configured SCCM site server.</span></li><li><b>Execute</b><span>A fixed read-only SSM document loads the Configuration Manager PowerShell provider.</span></li><li><b>Normalize</b><span>Devices, collections, deployments and software-update groups return as structured data.</span></li><li><b>Audit</b><span>Request, command, result and summary are recorded for operators.</span></li></ol></article><article><h3>Safe operating model</h3><ul><li><ShieldCheck/>No SCCM password or API key in the browser</li><li><ShieldCheck/>Only the approved OpsAgent document can run</li><li><ShieldCheck/>Target restricted to the tagged SCCM server</li><li><ShieldCheck/>Deployment actions remain separately approval-gated</li></ul></article></section> : tab === "Patch pipeline" && inventory ? <SccmPatchPipeline inventory={inventory}/> : <SimpleTable rows={rows || []} title={`SCCM ${tab}`} />}
  </section>;
}

function ConnectionsCenter() {
  const [settings, setSettings] = useState<Preferences | null>(null);
  const [status, setStatus] = useState("");
  const [awsConnection, setAwsConnection] = useState<Record<string, unknown> | null>(null);
  const [awsConfiguration, setAwsConfiguration] = useState<{region:string;execution_mode:string;allowed_actions:string[]}|null>(null);
  const [testingAws, setTestingAws] = useState(false);
  type ConnectionRecord = {provider:string;status:string;display_name:string;last_tested_at?:string;last_error?:string};
  const [connectionRecords, setConnectionRecords] = useState<ConnectionRecord[]>([]);
  const [selectedConnector, setSelectedConnector] = useState<{key:string;name:string;description:string}|null>(null);
  const [connectionMode, setConnectionMode] = useState<"api"|"gateway">("api");
  const [connectorForm, setConnectorForm] = useState({display_name:"",endpoint:"",credential_reference:"",platform:"windows"});
  const [connectorSecrets, setConnectorSecrets] = useState<Record<string,string>>({});
  const [enrollmentToken, setEnrollmentToken] = useState("");
  const [copiedConnectorValue, setCopiedConnectorValue] = useState<"url"|"token"|"">("");
  const [savingConnector, setSavingConnector] = useState(false);
  const [showAwsPolicy, setShowAwsPolicy] = useState(false);
  const awsInitialCheckStarted = useRef(false);
  const [connectionConfirmation, setConnectionConfirmation] = useState<{provider:string;action:"disconnect"|"delete"}|null>(null);
  const [awsPolicy, setAwsPolicy] = useState({region:"us-east-2",execution_mode:"validation",allowed_actions:"start_instance,stop_instance,reboot_instance",live_confirmation:""});
  const awsOperationOptions = [
    ["start_instance","Start instance","standard"], ["stop_instance","Stop instance","standard"],
    ["reboot_instance","Reboot instance","standard"], ["resize_instance","Resize instance","standard"],
    ["create_snapshot","Create snapshot","standard"], ["extend_volume","Extend EBS volume","standard"],
    ["detach_secondary_nic","Detach secondary NIC","sensitive"], ["terminate_instance","Terminate instance","destructive"],
    ["delete_snapshot","Delete snapshot","destructive"], ["delete_volume","Delete volume","destructive"],
  ] as const;
  useEffect(() => {
    let disposed = false;
    const loadConnections = async () => {
      const results = await Promise.allSettled([
        api<Preferences>("/settings"),
        api<ConnectionRecord[]>("/integrations/connections"),
        api<{region:string;execution_mode:string;allowed_actions:string[]}>("/connections/aws/configuration"),
      ]);
      if (disposed) return;
      if (results[0].status === "fulfilled") setSettings(results[0].value);
      if (results[1].status === "fulfilled") setConnectionRecords(results[1].value);
      if (results[2].status === "fulfilled") setAwsConfiguration(results[2].value);
      const failures = results.slice(0,2).filter((result) => result.status === "rejected").length;
      setStatus(failures ? `${failures} connection data source${failures > 1 ? "s are" : " is"} unavailable. Retrying automatically…` : "");
      if (results[1].status === "fulfilled" &&
          results[1].value.some((record)=>record.provider==="aws"&&record.status!=="disconnected") &&
          !awsInitialCheckStarted.current) {
        awsInitialCheckStarted.current = true;
        try {
          const verified = await api<Record<string,unknown>>("/connections/aws/test", {method:"POST"});
          if (!disposed) {
            setAwsConnection(verified);
            setConnectionRecords((current)=>current.map((record)=>record.provider==="aws"?{...record,status:"connected",last_error:undefined}:record));
          }
        } catch (error) {
          if (!disposed) {
            setAwsConnection(null);
            setConnectionRecords((current)=>current.map((record)=>record.provider==="aws"?{...record,status:"attention",last_error:(error as Error).message}:record));
            setStatus(`AWS needs attention: ${(error as Error).message}`);
          }
        }
      }
    };
    loadConnections();
    const retry = window.setInterval(loadConnections, 15000);
    return () => { disposed = true; window.clearInterval(retry); };
  }, []);
  if (!settings)
    return <div className="skeleton">{status || "Loading enterprise connections…"}</div>;
  const catalog = [
    [
      "Cloud operation targets",
      [
        ["aws", "Amazon Web Services", "EC2, EBS, Systems Manager and controlled cloud operations"],
        ["azure", "Microsoft Azure", "Virtual machines, disks, networks and Azure resources"],
        ["gcp", "Google Cloud", "Compute Engine and Google Cloud operations"],
        ["oracle", "Oracle Cloud", "OCI compute, storage and network operations"],
        ["ibmcloud", "IBM Cloud", "Virtual server and infrastructure operations"],
        ["alibaba", "Alibaba Cloud", "ECS inventory and controlled cloud operations"],
      ],
    ],
    [
      "Private infrastructure targets",
      [
        ["vmware", "VMware vSphere", "vCenter, ESXi, virtual machines and datastores"],
        ["nutanix", "Nutanix AHV", "Clusters, virtual machines and storage operations"],
        ["openstack", "OpenStack", "Compute, network and volume operations"],
        ["hyperv", "Microsoft Hyper-V", "Hosts, clusters and virtual machine lifecycle"],
        ["kubernetes", "Kubernetes / OpenShift", "Clusters, workloads and controlled remediation"],
      ],
    ],
    [
      "Endpoint and patch management",
      [
        ["sccm", "Microsoft SCCM / WSUS", "Collections, clients, software updates and patch orchestration"],
        ["intune", "Microsoft Intune", "Cloud-managed devices, compliance and applications"],
        ["ivanti", "Ivanti", "Endpoint inventory, patching and service management"],
      ],
    ],
    [
      "Operating system targets",
      [
        ["windows", "Windows Server", "Private Windows inventory and approved PowerShell runbooks"],
        ["linux", "Linux", "Private Linux inventory and allowlisted operational runbooks"],
      ],
    ],
    [
      "Datacenter, network and storage targets",
      [
        ["network", "Network and security", "Cisco, Fortinet, Palo Alto and F5 operations"],
        ["storage", "Enterprise storage", "NetApp, Pure Storage and Dell storage platforms"],
      ],
    ],
    [
      "Hardware management",
      [
        ["cisco", "Cisco UCS / Intersight", "Connect CIMC, UCS Manager or Intersight for chassis, blade, power, thermal and fault health"],
        ["dell", "Dell iDRAC / OpenManage", "Connect PowerEdge and OpenManage for chassis, server, component and lifecycle health"],
        ["hpe", "HPE iLO / OneView", "Connect ProLiant, Synergy and OneView for frames, blades and component health"],
      ],
    ],
    [
      "Alert sources",
      [
        ["grafana", "Grafana", "Alerts, dashboards and operational telemetry"],
        ["datadog", "Datadog", "Monitor events, acknowledgement and investigation context"],
        ["solarwinds", "SolarWinds", "Infrastructure alert events and operational context"],
        ["nagios", "Nagios", "Host and service notifications through secured webhooks"],
      ],
    ],
    [
      "Communication, approval and ITSM",
      [
        ["slack", "Slack", "Operator collaboration, approval and verified results"],
        ["gmail", "Gmail / Outlook", "Email request, approval and completion workflows"],
        ["servicenow", "ServiceNow", "Incidents, changes, approvals and CMDB"],
        ["jira", "Jira Service Management", "Issues, incidents, changes and automation"],
      ],
    ],
  ] as [string, string[][]][];
  const configurableConnectors = new Set([
    "aws","azure","gcp","oracle","ibmcloud","alibaba","vmware","nutanix",
    "openstack","hyperv","kubernetes","sccm","windows","linux","network",
    "storage","cisco","dell","hpe","grafana","datadog","solarwinds","nagios","slack","gmail",
  ]);
  async function toggle(key: string) {
    if (!settings) return;
    const current = settings;
    const next: Preferences = {
      ...current,
      extensions: { ...current.extensions, [key]: !current.extensions[key] },
    };
    setSettings(next);
    setStatus("Saving…");
    try {
      const saved = await api<Preferences>("/settings", {
        method: "PUT",
        body: JSON.stringify(next),
      });
      setSettings(saved);
      setStatus("Connection preference saved");
    } catch (error) {
      setStatus((error as Error).message);
    }
  }
  async function testAwsConnection() {
    setTestingAws(true);
    setStatus("Testing AWS role and EC2 inventory access…");
    try {
      const result = await api<Record<string, unknown>>("/connections/aws/test", { method: "POST" });
      setAwsConnection(result);
      setStatus("AWS connection verified");
    } catch (error) {
      setAwsConnection(null);
      setStatus((error as Error).message);
    } finally {
      setTestingAws(false);
    }
  }
  async function openConnector(key:string,name:string,description:string){
    if(key==="aws" && connectionRecords.some((record)=>record.provider==="aws"&&record.status!=="disconnected")){
      setStatus("");setShowAwsPolicy(true);
      try{
        const current=await api<{region:string;execution_mode:string;allowed_actions:string[]}>("/connections/aws/configuration");
        setAwsPolicy({region:current.region||"us-east-2",execution_mode:current.execution_mode||"validation",allowed_actions:(current.allowed_actions||[]).join(","),live_confirmation:""});
      }catch(error){setStatus((error as Error).message)}
      return;
    }
    const gatewayProviders = new Set(["sccm","hardware","cisco","dell","hpe","windows","linux","nutanix","openstack","hyperv","kubernetes","network","storage"]);
    setSelectedConnector({key,name,description});
    setConnectionMode(gatewayProviders.has(key)?"gateway":"api");
    setConnectorForm({display_name:`${name} connection`,endpoint:"",credential_reference:"",platform:"windows"});
    const connectorDefaults:Record<string,Record<string,string>>={aws:{region:"us-east-2",execution_mode:"validation",allowed_actions:"start_instance,stop_instance,reboot_instance"},slack:{allow_self_approval:"false"},gmail:{auth_method:"app_password",imap_host:"imap.gmail.com",imap_port:"993",imap_folder:"INBOX",smtp_host:"smtp.gmail.com",smtp_port:"587",poll_seconds:"30",approval_expiry_minutes:"30"},vmware:{port:"443",verify_ssl:"true"}};
    setConnectorSecrets(connectorDefaults[key]||{});
    setEnrollmentToken("");
    setCopiedConnectorValue("");
    setStatus("");
    if(key==="aws" && connectionRecords.some((record)=>record.provider==="aws"&&record.status!=="disconnected")){
      try{
        const current=await api<{region:string}>("/connections/aws/configuration");
        setConnectorSecrets({region:current.region||"us-east-2"});
      }catch(error){setStatus((error as Error).message)}
    }
  }
  function credentialFields(provider:string):Array<{key:string;label:string;secret?:boolean;placeholder?:string;options?:string[]}>{
    const awsRegions=["us-east-1","us-east-2","us-west-1","us-west-2","af-south-1","ap-east-1","ap-south-1","ap-south-2","ap-southeast-1","ap-southeast-2","ap-southeast-3","ap-southeast-4","ap-northeast-1","ap-northeast-2","ap-northeast-3","ca-central-1","ca-west-1","eu-central-1","eu-central-2","eu-west-1","eu-west-2","eu-west-3","eu-north-1","eu-south-1","eu-south-2","il-central-1","me-central-1","me-south-1","mx-central-1","sa-east-1"];
    const fields:Record<string,Array<{key:string;label:string;secret?:boolean;placeholder?:string;options?:string[]}>>={
      aws:[{key:"aws_access_key_id",label:"AWS access key ID",placeholder:"AKIA…"},{key:"aws_secret_access_key",label:"AWS secret access key",secret:true},{key:"region",label:"Primary AWS region",options:awsRegions},{key:"role_arn",label:"Cross-account role ARN",placeholder:"Optional"},{key:"external_id",label:"External ID",secret:true,placeholder:"Optional"}],
      azure:[{key:"tenant_id",label:"Tenant ID"},{key:"client_id",label:"Client ID"},{key:"client_secret",label:"Client secret",secret:true},{key:"subscription_id",label:"Subscription ID"}],
      gcp:[{key:"service_account_json",label:"Service account JSON",secret:true}],
      slack:[{key:"bot_token",label:"Bot user OAuth token",secret:true,placeholder:"xoxb-…"},{key:"app_token",label:"Socket Mode app token",secret:true,placeholder:"xapp-…"},{key:"channels",label:"Channels to monitor",placeholder:"C0123456789, #operations"},{key:"approvers",label:"Approved Slack users",placeholder:"U0123456789, U9876543210"},{key:"webhook_url",label:"Incoming webhook URL",secret:true,placeholder:"Optional"},{key:"signing_secret",label:"Signing secret",secret:true,placeholder:"Optional"},{key:"allow_self_approval",label:"Allow self-approval",options:["false","true"]}],
      gmail:[{key:"auth_method",label:"Authentication",options:["app_password"]},{key:"username",label:"Service mailbox",placeholder:"ops@company.com"},{key:"app_password",label:"Google app password",secret:true,placeholder:"16-character app password"},{key:"imap_folder",label:"Folder to monitor",placeholder:"INBOX"},{key:"request_senders",label:"Authorized request senders",placeholder:"operator@company.com, noc@company.com"},{key:"approvers",label:"Approved change approvers",placeholder:"manager@company.com, lead@company.com"},{key:"imap_host",label:"IMAP host",placeholder:"imap.gmail.com"},{key:"imap_port",label:"IMAP port",placeholder:"993"},{key:"smtp_host",label:"SMTP host",placeholder:"smtp.gmail.com"},{key:"smtp_port",label:"SMTP port",placeholder:"587"},{key:"poll_seconds",label:"Check for mail every (seconds)",placeholder:"30"},{key:"approval_expiry_minutes",label:"Approval expires after (minutes)",placeholder:"30"}],
      vmware:[{key:"endpoint",label:"vCenter hostname or IP"},{key:"username",label:"Service account username"},{key:"password",label:"Password",secret:true},{key:"port",label:"HTTPS port",placeholder:"443"},{key:"verify_ssl",label:"Verify TLS certificate",placeholder:"true"}],
      servicenow:[{key:"username",label:"Service account username"},{key:"password",label:"Password",secret:true},{key:"instance",label:"Instance URL"}],
      jira:[{key:"email",label:"Service account email"},{key:"api_token",label:"API token",secret:true}],
    };
    return fields[provider]||[{key:"username",label:"Service account username"},{key:"password",label:"Password or API token",secret:true}];
  }
  async function copyConnectorValue(kind:"url"|"token",value:string){
    await navigator.clipboard.writeText(value);
    setCopiedConnectorValue(kind);
    window.setTimeout(()=>setCopiedConnectorValue(""),1800);
  }
  async function saveConnector(event:FormEvent){
    event.preventDefault();
    if(!selectedConnector)return;
    setSavingConnector(true);setStatus("");
    try{
      if(selectedConnector.key==="aws"&&connectionRecords.some((record)=>record.provider==="aws"&&record.status!=="disconnected")){
        await api("/connections/aws/configuration",{method:"PUT",body:JSON.stringify({
          region:connectorSecrets.region,
          execution_mode:awsConfiguration?.execution_mode||"validation",
          allowed_actions:awsConfiguration?.allowed_actions||["start_instance","stop_instance","reboot_instance"],
          live_confirmation:"",
        })});
        setStatus("AWS region updated. Verifying access and synchronizing inventory…");
        const verified=await api<Record<string,unknown>>("/connections/aws/test",{method:"POST"});
        setAwsConnection(verified);
        await api("/connections/aws/sync",{method:"POST"});
        setStatus("AWS region updated and inventory synchronized successfully.");
        setSelectedConnector(null);
      }else if(connectionMode==="gateway"){
        const result=await api<{enrollment_token:string}>("/gateways/register",{method:"POST",body:JSON.stringify({name:connectorForm.display_name,platform:connectorForm.platform})});
        setEnrollmentToken(result.enrollment_token);
        setStatus("Gateway enrollment created. Copy this token now; it is shown only once.");
      }else if(selectedConnector.key==="grafana"){
        const result=await api<{webhook_url:string;bearer_token:string}>("/integrations/grafana/register",{method:"POST",body:JSON.stringify({name:connectorForm.display_name,platform:"windows"})});
        setConnectorForm((current)=>({...current,endpoint:result.webhook_url}));
        setEnrollmentToken(result.bearer_token);
        setStatus("Grafana webhook created. Add this URL and bearer token to a Grafana contact point, then send a test alert.");
      }else if(["datadog","solarwinds","nagios"].includes(selectedConnector.key)){
        const result=await api<{webhook_url:string;bearer_token:string}>(`/integrations/monitoring/${selectedConnector.key}/register`,{method:"POST",body:JSON.stringify({name:connectorForm.display_name,platform:"windows"})});
        setConnectorForm((current)=>({...current,endpoint:result.webhook_url}));
        setEnrollmentToken(result.bearer_token);
        setStatus(`${selectedConnector.name} webhook created. Configure it in the provider and send a test event.`);
      }else{
        const record=await api<{provider:string;status:string;display_name:string}>("/integrations/connections/secure",{method:"POST",body:JSON.stringify({provider:selectedConnector.key,display_name:connectorForm.display_name,endpoint:connectorForm.endpoint||null,configuration:{},credentials:connectorSecrets})});
        setConnectionRecords((current)=>[record,...current]);
        setConnectorSecrets({});
        if(selectedConnector.key==="aws"){
          setStatus("Credentials encrypted. Verifying AWS and importing inventory…");
          try{
            const verified=await api<Record<string,unknown>>("/connections/aws/test",{method:"POST"});
            setAwsConnection(verified);
            await api("/connections/aws/sync",{method:"POST"});
            setConnectionRecords((current)=>current.map((item,index)=>index===0?{...item,status:"connected"}:item));
            setStatus("AWS connected and inventory synchronized successfully.");
            setSelectedConnector(null);
          }catch(validationError){
            setStatus(`Credentials saved securely, but AWS verification failed: ${(validationError as Error).message}`);
          }
        }else if(["slack","gmail","vmware"].includes(selectedConnector.key)){
          setStatus(`Credentials encrypted. Testing ${selectedConnector.name}…`);
          try{
            await api(`/integrations/connections/${selectedConnector.key}/test`,{method:"POST"});
            setConnectionRecords((current)=>current.map((item,index)=>index===0?{...item,status:"connected"}:item));
            setStatus(selectedConnector.key==="gmail"?"Gmail mailbox and outbound mail verified. Tenant background processing is the next activation step.":`${selectedConnector.name} connected successfully.`);
            setSelectedConnector(null);
          }catch(validationError){setStatus(`Credentials saved securely, but validation failed: ${(validationError as Error).message}`)}
        }else {setStatus("Credentials encrypted and connection saved. Provider validation is still required.");setSelectedConnector(null)}
      }
    }catch(error){setStatus((error as Error).message)}finally{setSavingConnector(false)}
  }
  async function disconnectAws(){
    setSavingConnector(true);setStatus("");
    try{
      await api("/connections/aws/disconnect",{method:"POST"});
      setConnectionRecords((current)=>current.map((record)=>record.provider==="aws"?{...record,status:"disconnected"}:record));
      setAwsConnection(null);setAwsConfiguration(null);setSelectedConnector(null);setStatus("AWS disconnected. Reconnect with a new access key when required.");
    }catch(error){setStatus((error as Error).message)}finally{setSavingConnector(false)}
  }
  async function deleteAws(){
    setSavingConnector(true);setStatus("");
    try{
      await api("/connections/aws",{method:"DELETE"});
      setConnectionRecords((current)=>current.filter((record)=>record.provider!=="aws"));
      setAwsConnection(null);setAwsConfiguration(null);setSelectedConnector(null);setStatus("AWS connection, credentials and synchronized inventory removed.");
    }catch(error){setStatus((error as Error).message)}finally{setSavingConnector(false)}
  }
  async function testPlatform(provider:string){
    setStatus(`Verifying ${provider}…`);
    try{await api(`/integrations/connections/${provider}/test`,{method:"POST"});setConnectionRecords((current)=>current.map((record)=>record.provider===provider?{...record,status:"connected"}:record));setStatus(`${provider} connection verified.`)}catch(error){setStatus((error as Error).message)}
  }
  async function disconnectPlatform(provider:string){
    try{await api(`/integrations/connections/${provider}/disconnect`,{method:"POST"});setConnectionRecords((current)=>current.map((record)=>record.provider===provider?{...record,status:"disconnected"}:record));setStatus(`${provider} disconnected.`)}catch(error){setStatus((error as Error).message)}
  }
  async function deletePlatform(provider:string){
    try{await api(`/integrations/connections/${provider}`,{method:"DELETE"});setConnectionRecords((current)=>current.filter((record)=>record.provider!==provider));setStatus(`${provider} connection deleted.`)}catch(error){setStatus((error as Error).message)}
  }
  async function confirmConnectionAction(){
    if(!connectionConfirmation)return;
    const {provider,action}=connectionConfirmation;
    setConnectionConfirmation(null);
    if(provider==="aws") await (action==="disconnect"?disconnectAws():deleteAws());
    else await (action==="disconnect"?disconnectPlatform(provider):deletePlatform(provider));
  }
  async function saveAwsPolicy(event:FormEvent){
    event.preventDefault();setSavingConnector(true);setStatus("");
    try{
      await api("/connections/aws/configuration",{method:"PUT",body:JSON.stringify({region:awsPolicy.region,execution_mode:awsPolicy.execution_mode,allowed_actions:awsPolicy.allowed_actions.split(",").filter(Boolean),live_confirmation:awsPolicy.live_confirmation})});
      setAwsConfiguration({region:awsPolicy.region,execution_mode:awsPolicy.execution_mode,allowed_actions:awsPolicy.allowed_actions.split(",").filter(Boolean)});
      await api("/connections/aws/test",{method:"POST"});
      await api("/connections/aws/sync",{method:"POST"});
      setShowAwsPolicy(false);setStatus(`AWS policy saved in ${awsPolicy.execution_mode} mode and inventory synchronized.`);
    }catch(error){setStatus((error as Error).message)}finally{setSavingConnector(false)}
  }
  function beginAwsConnection(){
    setConnectionRecords((current)=>current.filter((record)=>!(record.provider==="aws"&&record.status==="disconnected")));
    void openConnector("aws","Amazon Web Services","Connect an AWS account with a restricted access key. OpsAgent will verify it and synchronize EC2 inventory.");
  }
  const latestConnectionByProvider = new Map<string,ConnectionRecord>();
  connectionRecords.forEach((record)=>{if(!latestConnectionByProvider.has(record.provider))latestConnectionByProvider.set(record.provider,record)});
  const featuredProviderRecords = ["slack","gmail"].map((provider)=>latestConnectionByProvider.get(provider)||{provider,status:"disconnected",display_name:provider==="slack"?"Slack":"Gmail / Outlook"});
  const otherConnectedRecords = [...latestConnectionByProvider.values()].filter((record)=>!["aws","slack","gmail"].includes(record.provider)&&record.status!=="disconnected");
  const platformIds = [...new Set(catalog.flatMap(([,items])=>items.map(([key])=>key)).filter((key)=>configurableConnectors.has(key)))];
  const connectedCount = platformIds.filter((provider)=>latestConnectionByProvider.get(provider)?.status==="connected").length;
  const disconnectedCount = platformIds.length-connectedCount;
  return (
    <section className="connections-center">
      <header className="connections-summary"><div><span className="eyebrow">INTEGRATIONS</span><h2>Connections</h2></div><div><span className="connected"><CheckCircle2/><b>{connectedCount}</b> Connected</span><span className="disconnected"><Cable/><b>{disconnectedCount}</b> Not connected</span></div></header>
      <section className="connected-platforms" aria-labelledby="connected-platforms-title">
      <div className="section-heading"><div><span className="eyebrow">CONNECTED PLATFORMS</span><h2 id="connected-platforms-title">Customer connections</h2><p>Manage credentials, verification and lifecycle from one place.</p></div></div>
      <section className="connector-quickstart">
        <div className="connector-logo aws"><FaAws /></div>
        <div><span className="eyebrow">CLOUD PLATFORM</span><h3>Amazon Web Services</h3><p>Configure encrypted IAM credentials, inventory region and guarded execution policy.</p></div>
        {connectionRecords.some((record)=>record.provider==="aws"&&record.status!=="disconnected") ? <div className="connector-result aws-connector-result"><div className="aws-connection-state"><span className={connectionRecords.find((record)=>record.provider==="aws")?.status==="attention"?"attention":""}>{connectionRecords.find((record)=>record.provider==="aws")?.status==="attention"?<AlertTriangle/>:<CheckCircle2 />} {awsConnection?"Connected":connectionRecords.find((record)=>record.provider==="aws")?.status==="attention"?"Attention required":"Verifying…"}</span><div className="aws-connection-facts"><b>{awsConfiguration?.region||"Region loading…"}</b><b className={awsConfiguration?.execution_mode==="live"?"live":"validation"}>{awsConfiguration?.execution_mode==="live"?"Live operations":"Validation only"}</b><strong>{awsConfiguration?.allowed_actions?.length||0} of {awsOperationOptions.length} operations enabled</strong></div></div>{connectionRecords.find((record)=>record.provider==="aws")?.last_error&&<div className="aws-connection-error"><AlertTriangle/><span>{connectionRecords.find((record)=>record.provider==="aws")?.last_error}</span></div>}<div className="aws-policy-summary">{awsOperationOptions.map(([key,label,risk])=>{const enabled=Boolean(awsConfiguration?.allowed_actions?.includes(key));return <span className={`${enabled?"enabled":"disabled"} ${risk}`} key={key}>{enabled?<CheckCircle2/>:<LockKeyhole/>}{label}<small>{enabled?"Enabled":"Disabled"}</small></span>})}</div><div className="connector-result-actions"><button type="button" className="manage" onClick={()=>openConnector("aws","Amazon Web Services","Change region and guarded execution policy without re-entering the protected access key.")}>Manage connection</button><button type="button" onClick={testAwsConnection} disabled={testingAws}>{testingAws?"Testing…":"Verify connection"}</button><button type="button" onClick={()=>setConnectionConfirmation({provider:"aws",action:"disconnect"})} disabled={savingConnector}>Disconnect</button><button type="button" className="danger" onClick={()=>setConnectionConfirmation({provider:"aws",action:"delete"})} disabled={savingConnector}>Delete</button></div></div> : <button onClick={beginAwsConnection}>{connectionRecords.some((record)=>record.provider==="aws")?"Reconnect AWS":"Connect AWS"}</button>}
      </section>
      {[...featuredProviderRecords,...otherConnectedRecords].map((record)=>{const catalogItem=catalog.flatMap(([,items])=>items).find(([key])=>key===record.provider);const name=catalogItem?.[1]||record.display_name;const description=catalogItem?.[2]||"Tenant-scoped enterprise connection";const active=record.status!=="disconnected";const facts=record.provider==="slack"?[["Transport","Socket Mode"],["Workflow","Requests & approvals"],["Security","Encrypted vault"]]:record.provider==="gmail"?[["Transport","IMAP + SMTP"],["Workflow","Email approvals"],["Security","Encrypted vault"]]:[["Connection","Tenant scoped"],["Control","RBAC governed"],["Evidence","Audited"]];return <article className={`connector-quickstart connected-service connector-${record.provider} ${active?"":"available"}`} key={record.provider}><div className={`connector-logo ${record.provider}`}>{connectorIcon(record.provider)}</div><div className="connected-service-identity"><span className="eyebrow">{active?"CONNECTED PLATFORM":"COMMUNICATION PLATFORM"}</span><h3>{name}</h3><p>{description}</p></div>{active?<><div className="connected-service-facts">{facts.map(([label,value])=><span key={label}><small>{label}</small><b>{value}</b></span>)}</div><div className="connector-result"><span><CheckCircle2/>{record.status==="connected"?"Connected":"Configured"}</span>{record.last_tested_at&&<small>Verified {new Date(record.last_tested_at).toLocaleString()}</small>}<div className="connector-result-actions"><button className="manage" onClick={()=>openConnector(record.provider,name,description)}>Manage</button><button onClick={()=>testPlatform(record.provider)}>Verify</button><button onClick={()=>setConnectionConfirmation({provider:record.provider,action:"disconnect"})}>Disconnect</button><button className="danger" onClick={()=>setConnectionConfirmation({provider:record.provider,action:"delete"})}>Delete</button></div></div></>:<button className="connector-setup-action" onClick={()=>openConnector(record.provider,name,description)}>Connect {name}</button>}</article>})}
      </section>
      {showAwsPolicy&&<div className="connector-wizard-backdrop" role="presentation" onMouseDown={()=>setShowAwsPolicy(false)}><section className="connector-wizard aws-connector-wizard aws-policy-wizard" role="dialog" aria-modal="true" onMouseDown={(event)=>event.stopPropagation()}><header><div><span>MANAGE CUSTOMER CONNECTION</span><h2>AWS connection and execution policy</h2><p>Choose the inventory region and explicitly allow only the operations this customer may perform.</p></div><button onClick={()=>setShowAwsPolicy(false)} aria-label="Close"><X/></button></header><form onSubmit={saveAwsPolicy}><div className="aws-policy-basics"><label>Primary AWS region<select value={awsPolicy.region} onChange={(event)=>setAwsPolicy({...awsPolicy,region:event.target.value})}>{credentialFields("aws").find((field)=>field.key==="region")?.options?.map((option)=><option key={option}>{option}</option>)}</select><small>Region containing the managed EC2 resources.</small></label><label>Execution mode<select value={awsPolicy.execution_mode} onChange={(event)=>setAwsPolicy({...awsPolicy,execution_mode:event.target.value,live_confirmation:""})}><option value="validation">Validation only (AWS DryRun)</option><option value="live">Live operations</option></select><small>Live mode changes real AWS resources after RBAC and exact confirmation.</small></label></div><fieldset className="aws-policy-actions"><legend><b>Approved operations</b><small>{awsPolicy.allowed_actions.split(",").filter(Boolean).length} of {awsOperationOptions.length} enabled</small></legend>{awsOperationOptions.map(([key,label,risk])=><label className={risk} key={key}><input type="checkbox" checked={awsPolicy.allowed_actions.split(",").includes(key)} onChange={(event)=>{const values=new Set(awsPolicy.allowed_actions.split(",").filter(Boolean));event.target.checked?values.add(key):values.delete(key);setAwsPolicy({...awsPolicy,allowed_actions:[...values].join(",")});}}/><span><b>{label}</b><small>{risk==="destructive"?"Destructive · confirmation and approval required":risk==="sensitive"?"Sensitive network change":"Guarded operation"}</small></span></label>)}</fieldset>{awsPolicy.execution_mode==="live"&&<label>Live-operation acknowledgement<input value={awsPolicy.live_confirmation} onChange={(event)=>setAwsPolicy({...awsPolicy,live_confirmation:event.target.value})} placeholder="ENABLE LIVE AWS OPERATIONS"/><small>Type exactly: ENABLE LIVE AWS OPERATIONS</small></label>}<div className="connector-secret-notice"><ShieldCheck/><span><b>Credential remains protected</b><small>The AWS access key and secret are encrypted and are never returned to the browser.</small></span></div>{status&&<p className="connector-wizard-status">{status}</p>}<footer><button type="button" onClick={()=>setShowAwsPolicy(false)}>Cancel</button><button className="primary-action" disabled={savingConnector||!awsPolicy.allowed_actions||awsPolicy.execution_mode==="live"&&awsPolicy.live_confirmation!=="ENABLE LIVE AWS OPERATIONS"}>{savingConnector?"Saving and verifying…":"Save policy and synchronize"}</button></footer></form></section></div>}
      {connectionConfirmation&&<div className="connector-wizard-backdrop" role="presentation" onMouseDown={()=>setConnectionConfirmation(null)}><section className="connection-confirmation" role="alertdialog" aria-modal="true" onMouseDown={(event)=>event.stopPropagation()}><div className="confirmation-icon"><AlertTriangle/></div><div><span>{connectionConfirmation.action==="delete"?"PERMANENT ACTION":"CONNECTION LIFECYCLE"}</span><h3>{connectionConfirmation.action==="delete"?"Delete":"Disconnect"} {connectionConfirmation.provider.toUpperCase()} connection?</h3><p>{connectionConfirmation.action==="delete"?"The encrypted credentials and synchronized connector records will be permanently removed. Retained audit history is not deleted.":"The stored credentials will be revoked and live synchronization will stop. Existing audit history will be retained."}</p></div><footer><button onClick={()=>setConnectionConfirmation(null)}>Cancel</button><button className={connectionConfirmation.action==="delete"?"danger":"primary-action"} onClick={confirmConnectionAction}>{connectionConfirmation.action==="delete"?"Delete connection":"Disconnect platform"}</button></footer></section></div>}
      {selectedConnector && <div className="connector-wizard-backdrop" role="presentation" onMouseDown={()=>setSelectedConnector(null)}><section className={`connector-wizard connector-${selectedConnector.key}-wizard ${selectedConnector.key==="aws"?"aws-connector-wizard":""}`} role="dialog" aria-modal="true" aria-labelledby="connector-wizard-title" onMouseDown={(event)=>event.stopPropagation()}><header><div><span>{connectionRecords.some((record)=>record.provider===selectedConnector.key)?"MANAGE CUSTOMER CONNECTION":"NEW CUSTOMER CONNECTION"}</span><h2 id="connector-wizard-title">{connectionRecords.some((record)=>record.provider===selectedConnector.key)?"Update":"Connect"} {selectedConnector.name}</h2><p>{selectedConnector.description}</p></div><button onClick={()=>setSelectedConnector(null)} aria-label="Close"><X/></button></header>{selectedConnector.key!=="aws"&&<div className="connector-mode"><button className={connectionMode==="api"?"active":""} onClick={()=>setConnectionMode("api")}><Cloud/><b>API connection</b><small>Encrypted application credential</small></button><button className={connectionMode==="gateway"?"active":""} onClick={()=>setConnectionMode("gateway")}><Server/><b>Customer gateway</b><small>Private VMware, SCCM, Windows or Linux</small></button></div>}<form onSubmit={saveConnector}>{selectedConnector.key==="aws"&&<div className="aws-setup-intro"><div><FaAws/><span><b>{connectionRecords.some((record)=>record.provider==="aws")?"Update inventory region":"Connect with restricted IAM credentials"}</b><small>{connectionRecords.some((record)=>record.provider==="aws")?"The encrypted access key remains protected and will not be displayed or replaced.":"OpsAgent verifies access and imports EC2 inventory after saving."}</small></span></div></div>}{!(selectedConnector.key==="aws"&&connectionRecords.some((record)=>record.provider==="aws"))&&<label>Connection name<input required value={connectorForm.display_name} onChange={(event)=>setConnectorForm({...connectorForm,display_name:event.target.value})}/></label>}{connectionMode==="api"?<>{selectedConnector.key==="aws"&&connectionRecords.some((record)=>record.provider==="aws")?<label>Primary AWS region<select required value={connectorSecrets.region||"us-east-2"} onChange={(event)=>setConnectorSecrets({...connectorSecrets,region:event.target.value})}>{credentialFields("aws").find((field)=>field.key==="region")?.options?.map((option)=><option value={option} key={option}>{option}</option>)}</select><small>Select the region where your EC2 instances are running.</small></label>:["grafana","datadog","solarwinds","nagios"].includes(selectedConnector.key)?<label>OpsAgent webhook URL<input readOnly value={connectorForm.endpoint} placeholder="Generated after you select Create webhook"/><small>After creation, copy this URL and bearer token into the monitoring provider.</small></label>:<>{selectedConnector.key!=="aws"&&<label>Provider endpoint <small>Optional for public SaaS APIs</small><input value={connectorForm.endpoint} onChange={(event)=>setConnectorForm({...connectorForm,endpoint:event.target.value})} placeholder="https://api.company.example"/></label>}<div className="connector-secret-fields"><div className="connector-secret-notice"><ShieldCheck/><span><b>Encrypted credential vault</b><small>Values are encrypted before storage and are never displayed again.</small></span></div>{credentialFields(selectedConnector.key).map((field)=><label key={field.key}>{field.label}{field.options?<select required value={connectorSecrets[field.key]||"us-east-2"} onChange={(event)=>setConnectorSecrets({...connectorSecrets,[field.key]:event.target.value})}>{field.options.map((option)=><option value={option} key={option}>{option}</option>)}</select>:<input required={!field.placeholder?.includes("Optional")} type={field.secret?"password":"text"} autoComplete="new-password" value={connectorSecrets[field.key]||""} onChange={(event)=>setConnectorSecrets({...connectorSecrets,[field.key]:event.target.value})} placeholder={field.placeholder||""}/>}</label>)}</div></>}</>:<label>Gateway platform<select value={connectorForm.platform} onChange={(event)=>setConnectorForm({...connectorForm,platform:event.target.value})}><option value="windows">Windows</option><option value="linux">Linux</option><option value="kubernetes">Kubernetes</option></select><small>The gateway makes outbound HTTPS connections; no inbound firewall port is required.</small></label>}{enrollmentToken&&<div className="gateway-token"><ShieldCheck/><span><b>{["grafana","datadog","solarwinds","nagios"].includes(selectedConnector.key)?"One-time webhook bearer token":"One-time enrollment token"}</b><code>{enrollmentToken}</code><small>{["grafana","datadog","solarwinds","nagios"].includes(selectedConnector.key)?"Copy it into the provider's Authorization header credentials. It will not be shown again.":"Copy it now and use it during gateway installation."}</small></span></div>}{status&&<p className="connector-wizard-status">{status}</p>}<footer><button type="button" onClick={()=>setSelectedConnector(null)}>Cancel</button><button className="primary-action" disabled={savingConnector||Boolean(enrollmentToken)}>{savingConnector?(selectedConnector.key==="aws"?"Verifying and syncing…":"Connecting…"):connectionMode==="api"?(["grafana","datadog","solarwinds","nagios"].includes(selectedConnector.key)?"Create webhook":selectedConnector.key==="aws"?(connectionRecords.some((record)=>record.provider==="aws")?"Update region and synchronize":"Connect and synchronize"):"Encrypt and connect"):"Generate enrollment"}</button></footer></form></section></div>}
      {selectedConnector && enrollmentToken && <aside className="connector-copy-panel" role="dialog" aria-modal="true" aria-labelledby="credentials-title"><header><div className="credential-success"><CheckCircle2/></div><span><small>STEP 3 OF 4 · CREDENTIALS</small><b id="credentials-title">Connect {selectedConnector.name}</b><p>Your secure endpoint is ready. Copy both values before continuing.</p></span><button type="button" onClick={()=>setSelectedConnector(null)} aria-label="Close"><X/></button></header><div className="credential-progress"><i className="done">1</i><span/><i className="done">2</i><span/><i className="active">3</i><span/><i>4</i></div><label>Webhook endpoint<div><code>{connectorForm.endpoint}</code><button type="button" onClick={()=>copyConnectorValue("url",connectorForm.endpoint)}><Copy/>{copiedConnectorValue==="url"?"Copied":"Copy URL"}</button></div><small>Paste this URL into the monitoring platform’s webhook or contact-point configuration.</small></label><label>Authorization bearer token<div><code>{enrollmentToken}</code><button type="button" onClick={()=>copyConnectorValue("token",enrollmentToken)}><Copy/>{copiedConnectorValue==="token"?"Copied":"Copy token"}</button></div><small>Add it as an Authorization header using the Bearer scheme.</small></label><div className="credential-security"><ShieldCheck/><span><b>Secret handling</b><p>This token is shown once. OpsAgent stores only its cryptographic hash and cannot display it again.</p></span></div><footer><button type="button" onClick={()=>setSelectedConnector(null)}>Done for now</button><button type="button" className="primary-action" onClick={()=>setStatus("Configure the provider with these credentials, send a test alert, then return to verify the connection.")}>Continue to verification <ChevronRight/></button></footer></aside>}
      {catalog.map(([group, items]) => (
        <section className="connection-group" key={group}>
          <div className="section-heading">
            <div>
              <h2>{group}</h2>
              <p>{group.includes("Alert") || group.includes("Communication") ? "Supporting signals, collaboration and governance" : "Primary operation targets with RBAC, approval and audit controls"}</p>
            </div>
          </div>
          <div className="connection-grid">
            {items.filter(([key])=>configurableConnectors.has(key)&&!["aws","slack","gmail"].includes(key)&&!connectionRecords.some((record)=>record.provider===key&&record.status!=="disconnected")).map(([key, name, description]) => (
              <article key={key} className={`connector-platform connector-${key}`}>
                <div className="extension-icon">{connectorIcon(key)}</div>
                <div>
                  <strong>{name}</strong>
                  <p>{description}</p>
                  <small>{connectionRecords.find((record)=>record.provider===key)?.status==="connected" ? "Connected · credential protected" : connectionRecords.some((record)=>record.provider===key) ? "Saved · verification required" : "Available to configure"}</small>
                </div>
                {connectionRecords.some((record)=>record.provider===key&&record.status!=="disconnected")?<div className="connector-card-actions"><button className="connector-setup-action connected" onClick={() => openConnector(key,name,description)}>Manage</button><button onClick={()=>testPlatform(key)}>Verify</button><button onClick={()=>disconnectPlatform(key)}>Disconnect</button><button className="danger" onClick={()=>deletePlatform(key)}>Delete</button></div>:<button className="connector-setup-action" onClick={() => openConnector(key,name,description)}>{connectionRecords.some((record)=>record.provider===key)?"Reconnect":"Connect"}</button>}
              </article>
            ))}
          </div>
        </section>
      ))}
      {status && <div className="connection-toast">{status}</div>}
    </section>
  );
}

function SettingsCenter() {
  const [settings, setSettings] = useState<Preferences | null>(null);
  const [section, setSection] = useState("Appearance");
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const [aiConfig, setAiConfig] = useState<AiConfiguration>({mode:"platform",provider:"openai",model:"gpt-4o-mini",endpoint:"",api_key_configured:false,ready:false});
  const [aiKey, setAiKey] = useState("");
  const [savingAi, setSavingAi] = useState(false);
  useEffect(() => {
    api<Preferences>("/settings").then((x) => {
      setSettings(x);
      applyPreferences(x);
    });
    api<AiConfiguration>("/settings/ai").then(setAiConfig).catch((error)=>setStatus(error.message));
  }, []);
  if (!settings)
    return <div className="skeleton">Loading workspace settings…</div>;
  const update = (patch: Partial<Preferences>) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    applyPreferences(next);
    setStatus("Unsaved changes");
  };
  const toggleExtension = (name: string) =>
    update({
      extensions: {
        ...settings.extensions,
        [name]: !settings.extensions[name],
      },
    });
  async function save() {
    setSaving(true);
    try {
      const saved = await api<Preferences>("/settings", {
        method: "PUT",
        body: JSON.stringify(settings),
      });
      setSettings(saved);
      applyPreferences(saved);
      setStatus("Settings saved to PostgreSQL");
    } catch (e) {
      setStatus((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function saveAiConfiguration() {
    setSavingAi(true);setStatus("");
    try {
      const saved=await api<AiConfiguration>("/settings/ai",{method:"PUT",body:JSON.stringify({
        mode:aiConfig.mode,provider:aiConfig.mode==="self_hosted"?"openai_compatible":"openai",
        model:aiConfig.model,endpoint:aiConfig.endpoint||null,api_key:aiKey||null,
      })});
      setAiConfig(saved);setAiKey("");setStatus("AI configuration encrypted and activated for this organization");
    } catch(error){setStatus((error as Error).message)} finally {setSavingAi(false)}
  }
  const extensions = [
    ["aws", "AWS", "EC2 inventory and guarded cloud operations"],
    ["azure", "Azure", "Virtual machines and Azure resource discovery"],
    ["vmware", "VMware", "vCenter, ESXi and virtual-machine inventory"],
    ["sccm", "SCCM", "Microsoft Configuration Manager integration"],
    ["intune", "Microsoft Intune", "Cloud endpoint management and compliance"],
    ["ivanti", "Ivanti", "Endpoint and service management"],
    ["servicenow", "ServiceNow", "Incidents, changes and CMDB workflows"],
    ["jira", "Jira Service Management", "Issues, incidents and approvals"],
    ["slack", "Slack", "Alert intake and operational collaboration"],
    ["gmail", "Gmail", "Email alert ingestion and response"],
    ["grafana", "Grafana", "Metrics, alerts and observability"],
    [
      "hardware",
      "Datacenter hardware",
      "Cisco UCS, Dell and HPE infrastructure",
    ],
  ];
  return (
    <section className="settings-shell">
      <aside className="settings-nav">
        <div>
          <SettingsIcon />
          <strong>Workspace settings</strong>
        </div>
        {[
          "Appearance",
          "AI & models",
          "Extensions",
          "Notifications",
          "Regional",
        ].map((x) => (
          <button
            className={section === x ? "selected" : ""}
            onClick={() => setSection(x)}
            key={x}
          >
            {x}
          </button>
        ))}
      </aside>
      <div className="settings-content">
        {section === "Appearance" && (
          <>
            <div className="settings-heading">
              <div>
                <h2>Appearance</h2>
                <p>Personalize how the control plane looks and feels.</p>
              </div>
              <MonitorCog />
            </div>
            <SettingGroup
              title="Theme"
              description="Applied immediately and saved to your account."
            >
              <div className="choice-grid">
                {[
                  ["dark", "Dark"],
                  ["light", "Light"],
                  ["system", "Use system"],
                ].map(([value, label]) => (
                  <button
                    className={settings.theme === value ? "chosen" : ""}
                    onClick={() => update({ theme: value })}
                    key={value}
                  >
                    <span className={`theme-preview ${value}`} />
                    <strong>{label}</strong>
                  </button>
                ))}
              </div>
            </SettingGroup>
            <SettingGroup
              title="Text size"
              description="Change navigation, tables and operational content."
            >
              <Segmented
                values={[
                  ["compact", "Small"],
                  ["comfortable", "Default"],
                  ["large", "Large"],
                ]}
                current={settings.font_size}
                onChange={(x) => update({ font_size: x })}
              />
            </SettingGroup>
            <SettingGroup
              title="Information density"
              description="Choose comfortable or compact enterprise layouts."
            >
              <Segmented
                values={[
                  ["comfortable", "Comfortable"],
                  ["compact", "Compact"],
                ]}
                current={settings.density}
                onChange={(x) => update({ density: x })}
              />
            </SettingGroup>
          </>
        )}
        {section === "AI & models" && (
          <>
            <div className="settings-heading">
              <div>
                <h2>AI & models</h2>
                <p>Choose platform billing, your own API key, or an OpenAI-compatible model endpoint.</p>
              </div>
              <Bot />
            </div>
            <div className="ai-config-layout">
              <div className="ai-mode-list">
                <p>CONNECTION TYPE</p>
                {[["platform","Pay as you go","Managed by OpsAgent"],["byok","Use my API key","OpenAI account billing"],["self_hosted","Use my own model","OpenAI-compatible endpoint"]].map(([mode,title,description])=><button className={aiConfig.mode===mode?"selected":""} onClick={()=>setAiConfig({...aiConfig,mode:mode as AiConfiguration["mode"],provider:mode==="self_hosted"?"openai_compatible":"openai"})} key={mode}><span className="ai-radio">{aiConfig.mode===mode&&<i/>}</span><span><strong>{title}</strong><small>{description}</small></span></button>)}
              </div>
              <div className="ai-config-panel">
                <header><div><span className="ai-provider-icon"><Bot/></span><div><h3>{aiConfig.mode==="platform"?"OpsAgent managed AI":aiConfig.mode==="byok"?"OpenAI API key":"Custom model endpoint"}</h3><p>{aiConfig.mode==="platform"?"Use the managed platform model with organization usage tracking.":aiConfig.mode==="byok"?"Charges are billed directly to your OpenAI account.":"Connect Ollama, vLLM, LocalAI, or another compatible service."}</p></div></div><span className={`ai-readiness ${aiConfig.ready?"ready":""}`}>{aiConfig.ready?"Ready":"Setup required"}</span></header>
                <div className="ai-fields">
                  <label>Model name<input value={aiConfig.model} onChange={(e)=>setAiConfig({...aiConfig,model:e.target.value})} placeholder="gpt-4o-mini or deployment name"/></label>
                  {aiConfig.mode==="self_hosted"&&<label>API endpoint<input type="url" value={aiConfig.endpoint} onChange={(e)=>setAiConfig({...aiConfig,endpoint:e.target.value})} placeholder="https://models.company.com/v1"/></label>}
                  {aiConfig.mode!=="platform"&&<label>API key <span>{aiConfig.api_key_configured?"Encrypted key saved":"Required for OpenAI"}</span><input type="password" value={aiKey} onChange={(e)=>setAiKey(e.target.value)} placeholder={aiConfig.api_key_configured?"Leave blank to keep existing key":aiConfig.mode==="self_hosted"?"Optional for trusted endpoints":"sk-…"} autoComplete="new-password"/></label>}
                </div>
                <footer><div><ShieldCheck/><span><b>Stored securely</b><small>Secrets stay encrypted and are never returned to the browser.</small></span></div><button onClick={saveAiConfiguration} disabled={savingAi||!aiConfig.model||aiConfig.mode==="byok"&&!aiKey&&!aiConfig.api_key_configured||aiConfig.mode==="self_hosted"&&!aiConfig.endpoint}>{savingAi?"Saving…":"Save configuration"}</button></footer>
                {status&&<p className="ai-inline-message">{status}</p>}
              </div>
            </div>
          </>
        )}
        {section === "Extensions" && (
          <>
            <div className="settings-heading">
              <div>
                <h2>Extensions</h2>
                <p>
                  Control which enterprise connectors appear in this workspace.
                </p>
              </div>
              <Plug />
            </div>
            <div className="extension-grid">
              {extensions.map(([key, name, description]) => (
                <article key={key}>
                  <div className="extension-icon">
                    <Boxes />
                  </div>
                  <div>
                    <strong>{name}</strong>
                    <p>{description}</p>
                    <small>
                      {settings.extensions[key]
                        ? "Enabled for workspace"
                        : "Disabled"}
                    </small>
                  </div>
                  <button
                    className={`toggle ${settings.extensions[key] ? "on" : ""}`}
                    onClick={() => toggleExtension(key)}
                    aria-label={`Toggle ${name}`}
                  >
                    <i />
                  </button>
                </article>
              ))}
            </div>
            <p className="settings-note">
              Enabling an extension exposes its workspace. Provider credentials
              and permissions must still be configured securely on the API or
              customer agent.
            </p>
          </>
        )}
        {section === "Notifications" && (
          <>
            <div className="settings-heading">
              <div>
                <h2>Notifications</h2>
                <p>Choose the events that require your attention.</p>
              </div>
              <Bell />
            </div>
            <ToggleRow
              title="Email notifications"
              description="Receive assigned alerts, approvals and incident updates."
              value={settings.email_notifications}
              onChange={() =>
                update({ email_notifications: !settings.email_notifications })
              }
            />
            <ToggleRow
              title="Operation notifications"
              description="Notify me when a guarded infrastructure operation completes or fails."
              value={settings.operation_notifications}
              onChange={() =>
                update({
                  operation_notifications: !settings.operation_notifications,
                })
              }
            />
          </>
        )}
        {section === "Regional" && (
          <>
            <div className="settings-heading">
              <div>
                <h2>Regional settings</h2>
                <p>Format operational timestamps for your location.</p>
              </div>
              <SlidersHorizontal />
            </div>
            <div className="settings-form">
              <label>
                Timezone
                <select
                  value={settings.timezone}
                  onChange={(e) => update({ timezone: e.target.value })}
                >
                  <option>Asia/Kolkata</option>
                  <option>UTC</option>
                  <option>America/New_York</option>
                  <option>Europe/London</option>
                  <option>Asia/Singapore</option>
                </select>
              </label>
              <label>
                Date format
                <select
                  value={settings.date_format}
                  onChange={(e) => update({ date_format: e.target.value })}
                >
                  <option>DD MMM YYYY</option>
                  <option>DD/MM/YYYY</option>
                  <option>MM/DD/YYYY</option>
                  <option>YYYY-MM-DD</option>
                </select>
              </label>
            </div>
          </>
        )}
        {section !== "AI & models" && <div className="settings-save">
          <span>{status || "Preferences are stored per user."}</span>
          <button onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>}
      </div>
    </section>
  );
}
function SettingGroup({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="setting-group">
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}
function Segmented({
  values,
  current,
  onChange,
}: {
  values: string[][];
  current: string;
  onChange: (x: string) => void;
}) {
  return (
    <div className="segmented">
      {values.map(([value, label]) => (
        <button
          className={current === value ? "active" : ""}
          onClick={() => onChange(value)}
          key={value}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
function ToggleRow({
  title,
  description,
  value,
  onChange,
}: {
  title: string;
  description: string;
  value: boolean;
  onChange: () => void;
}) {
  return (
    <div className="toggle-row">
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
      <button className={`toggle ${value ? "on" : ""}`} onClick={onChange}>
        <i />
      </button>
    </div>
  );
}
function CodeBlock({ children }: { children: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="code-block">
      <button
        onClick={() => {
          navigator.clipboard.writeText(children);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        }}
      >
        <Copy />
        {copied ? "Copied" : "Copy"}
      </button>
      <pre>{children}</pre>
    </div>
  );
}

function Documentation() {
  const [section, setSection] = useState(() => {
    const requested = sessionStorage.getItem("opsagent_docs_section");
    sessionStorage.removeItem("opsagent_docs_section");
    return requested || "Documentation home";
  });
  const [docsQuery, setDocsQuery] = useState("");
  const sections = [
    "Documentation home",
    "Overview",
    "Capability matrix",
    "Integrations",
    "AWS connection model",
    "Datadog",
    "Integration runbook",
    "Architecture",
    "Control plane",
    "Customer agent",
    "Connect infrastructure",
    "SCCM connector",
    "Choose an LLM",
    "Security",
    "Production checklist",
  ];
  const visibleSections = sections.filter((item) =>
    item.toLowerCase().includes(docsQuery.trim().toLowerCase()),
  );
  const openSection = (nextSection: string) => {
    setSection(nextSection);
    requestAnimationFrame(() => {
      document.querySelector(".authenticated-docs-view")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };
  return (
    <div className="public-docs-view authenticated-docs-view">
    <section className={`docs-portal ${section === "Documentation home" ? "docs-home-mode" : ""}`}>
      {section === "Documentation home" ? <header className="docs-home-hero">
        <span>OPSAGENT ONE DOCUMENTATION</span>
        <h1>Welcome to OpsAgent One Documentation</h1>
        <p>Enterprise guidance for monitoring, cloud lifecycle management, operating-system administration and patch compliance.</p>
        <div className="docs-home-search"><Search/><input value={docsQuery} onChange={(event) => setDocsQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && visibleSections[0]) openSection(visibleSections[0]); }} placeholder="Search architecture, integrations, security and operations"/><kbd>/</kbd><button onClick={() => visibleSections[0] && openSection(visibleSections[0])}>Search</button><button className="docs-ask-ai" onClick={() => openSection("Overview")}><Sparkles/> Ask OpsAgent</button></div>
        <small>Popular: <button onClick={() => openSection("AWS connection model")}>AWS connection</button><button onClick={() => openSection("SCCM connector")}>SCCM integration</button><button onClick={() => openSection("Security")}>Security architecture</button><button onClick={() => openSection("Production checklist")}>Production readiness</button></small>
      </header> : null}
      <div className="docs-shell">
      <aside className="docs-nav">
        <div className="docs-nav-title"><strong>OpsAgent Docs</strong></div>
        <label className="docs-nav-search"><Search/><input value={docsQuery} onChange={(event) => setDocsQuery(event.target.value)} placeholder="Search documentation..."/><kbd>/</kbd></label>
        <span className="docs-nav-group">ESSENTIALS</span>
        {visibleSections.map((x) => (
          <button
            className={section === x ? "selected" : ""}
            onClick={() => openSection(x)}
            key={x}
          >
            {x}
          </button>
        ))}
      </aside>
      <article className="docs-content">
        {section === "Documentation home" && (
          <>
            <div className="docs-onboarding-path">
              <button onClick={() => setSection("Overview")}><b>01</b><span><strong>Establish the architecture</strong><small>Define the control plane, customer agent and trust boundaries.</small><em>Platform overview <ChevronRight/></em></span></button>
              <button onClick={() => setSection("Connect infrastructure")}><b>02</b><span><strong>Connect the enterprise estate</strong><small>Register infrastructure using least-privilege identities.</small><em>Connection guidance <ChevronRight/></em></span></button>
              <button onClick={() => setSection("Production checklist")}><b>03</b><span><strong>Operationalize governance</strong><small>Validate policy, approval, audit and production readiness.</small><em>Production readiness <ChevronRight/></em></span></button>
            </div>
            <div className="docs-catalog">
              <section className="docs-catalog-wide"><h2><Eye/> Monitoring and incident response <small>(6)</small></h2><div className="docs-catalog-card"><div><h4>INFRASTRUCTURE INTELLIGENCE</h4><button onClick={() => setSection("Overview")}><b>Infrastructure monitoring</b><span>Assess service health, availability and infrastructure performance.</span></button><button onClick={() => setSection("Architecture")}><b>Event correlation</b><span>Correlate alerts with infrastructure and operational context.</span></button></div><div><h4>INCIDENT OPERATIONS</h4><button onClick={() => setSection("Datadog")}><b>Monitoring integrations</b><span>Receive and govern events from enterprise monitoring platforms.</span></button><button onClick={() => setSection("Integration runbook")}><b>Investigation runbooks</b><span>Collect diagnostic evidence through controlled automation.</span></button></div><div><h4>RESPONSE GOVERNANCE</h4><button onClick={() => setSection("Control plane")}><b>Approval workflows</b><span>Apply human authorization before infrastructure changes.</span></button><button onClick={() => setSection("Security")}><b>Operational audit</b><span>Retain request, approval, execution and verification evidence.</span></button></div></div></section>
              <section><h2><Cloud/> Cloud operations <small>(5)</small></h2><div className="docs-catalog-card docs-catalog-stack"><div><h4>CLOUD LIFECYCLE</h4><button onClick={() => setSection("AWS connection model")}><b>AWS connection model</b><span>Configure temporary, role-based access with External ID protection.</span></button><button onClick={() => setSection("Connect infrastructure")}><b>Infrastructure onboarding</b><span>Register cloud estates using customer connectors.</span></button><button onClick={() => setSection("Capability matrix")}><b>Resource operations</b><span>Review supported inventory and lifecycle capabilities.</span></button></div></div></section>
              <section><h2><MonitorCog/> Operating system operations <small>(5)</small></h2><div className="docs-catalog-card docs-catalog-stack"><div><h4>SERVER ADMINISTRATION</h4><button onClick={() => setSection("Customer agent")}><b>Customer agent deployment</b><span>Deploy the controlled execution agent inside the enterprise boundary.</span></button><button onClick={() => setSection("Architecture")}><b>Windows and Linux operations</b><span>Execute allowlisted administration and diagnostic runbooks.</span></button><button onClick={() => setSection("Control plane")}><b>Execution governance</b><span>Control authorization, execution and final-state verification.</span></button></div></div></section>
              <section><h2><CheckCircle2/> Patching and compliance <small>(4)</small></h2><div className="docs-catalog-card docs-catalog-stack"><div><h4>PATCH GOVERNANCE</h4><button onClick={() => setSection("SCCM connector")}><b>SCCM and WSUS</b><span>Connect endpoint inventory and managed patch workflows.</span></button><button onClick={() => setSection("Production checklist")}><b>Production readiness</b><span>Validate change controls, deployment rings and compliance evidence.</span></button></div></div></section>
              <section><h2><ShieldCheck/> Platform security <small>(4)</small></h2><div className="docs-catalog-card docs-catalog-stack"><div><h4>ENTERPRISE CONTROL</h4><button onClick={() => setSection("Security")}><b>Identity and authorization</b><span>Implement least privilege, MFA, RBAC and credential isolation.</span></button><button onClick={() => setSection("Choose an LLM")}><b>AI governance</b><span>Select approved models and enforce enterprise trust boundaries.</span></button></div></div></section>
            </div>
          </>
        )}
        {section === "Overview" && (
          <>
            <p className="eyebrow">GETTING STARTED</p>
            <h2>Deploy OpsAgent in your enterprise</h2>
            <p className="lead">
              Run one central control plane and install a lightweight OpsAgent
              inside each customer network. Agents connect outbound, keep
              credentials locally and enforce customer policy.
            </p>
            <div className="doc-steps">
              {[
                ["1", "Deploy control plane"],
                ["2", "Register customer agent"],
                ["3", "Connect infrastructure"],
                ["4", "Choose approved LLM"],
                ["5", "Enable guarded operations"],
              ].map(([n, x]) => (
                <div key={n}>
                  <b>{n}</b>
                  <span>{x}</span>
                </div>
              ))}
            </div>
            <Callout title="Enterprise trust boundary">
              Provider credentials never belong in the browser or AI prompt.
              Customer agents retain secrets and execute only signed, authorized
              requests.
            </Callout>
          </>
        )}
        {section === "Capability matrix" && (
          <>
            <p className="eyebrow">PRODUCT SCOPE</p>
            <h2>What OpsAgent supports today</h2>
            <p className="lead">Five capability pillars with clear maturity labels for working integrations, foundations and roadmap commitments.</p>
            <div className="maturity-legend"><span className="live">Live</span><small>Working end to end</small><span className="foundation">Foundation</span><small>UI, model or partial connector exists</small><span className="roadmap">Roadmap</span><small>Not yet implemented</small></div>
            <div className="capability-matrix">
              <article><header><Cloud/><h3>Cloud operations</h3></header><p>Operate resources through the web app, agent, Slack or email with approval and verification.</p><ul><li><b>AWS</b><span className="live">Live</span></li><li><b>Azure and VMware</b><span className="foundation">Foundation</span></li><li><b>GCP and Oracle Cloud</b><span className="roadmap">Roadmap</span></li></ul></article>
              <article><header><Activity/><h3>Monitoring and incident response</h3></header><p>Acknowledge alerts, collect context and coordinate recovery through communication channels.</p><ul><li><b>Slack and Gmail workflows</b><span className="live">Live</span></li><li><b>Grafana incident flow</b><span className="live">Demo</span></li><li><b>Datadog, SolarWinds, Nagios, Outlook</b><span className="roadmap">Connector required</span></li></ul></article>
              <article><header><CheckCircle2/><h3>Patch intelligence</h3></header><p>Coordinate KB intake, test rings, change approval, deployment status and validation.</p><ul><li><b>SCCM inventory</b><span className="live">Live</span></li><li><b>Patch governance pipeline</b><span className="live">Built</span></li><li><b>SCCM deployment mutation</b><span className="foundation">Next stage</span></li><li><b>Intune and Ivanti</b><span className="roadmap">Roadmap</span></li></ul></article>
              <article><header><Terminal/><h3>Windows and Linux automation</h3></header><p>Use typed, allowlisted runbooks for recurring server administration and verified execution.</p><ul><li><b>Windows SSM operations</b><span className="live">Live</span></li><li><b>Windows operation catalog</b><span className="foundation">Expanding</span></li><li><b>Linux execution catalog</b><span className="foundation">Foundation</span></li></ul></article>
              <article><header><ShieldCheck/><h3>Governance, ITSM and evidence</h3></header><p>Apply tenant RBAC, approvals, audit history and change coordination across every domain.</p><ul><li><b>Organizations, RBAC and audit</b><span className="live">Live</span></li><li><b>Approval and verification</b><span className="live">Live</span></li><li><b>ServiceNow and Jira APIs</b><span className="roadmap">Connector required</span></li></ul></article>
            </div>
            <Callout title="Product language rule">Only capabilities marked Live are completed integrations. Foundation and Roadmap items describe the implementation direction.</Callout>
          </>
        )}
        {section === "Integrations" && (
          <>
            <p className="docs-breadcrumb">Docs / Integrations</p>
            <h2>Integrations</h2>
            <p className="lead">Connect the systems your teams already use. Every guide documents prerequisites, least-privilege access, configuration, validation, troubleshooting, credential rotation and removal.</p>
            <div className="integration-doc-grid">
              {[
                ["AWS", "Cloud operations", "Live", "Role-based access with External ID and tagged targets"],
                ["SCCM / WSUS", "Patch intelligence", "Inventory live", "Read-only inventory with patch workflow"],
                ["Grafana", "Monitoring", "Demo", "Alert webhook to acknowledgement and investigation"],
                ["Slack", "Collaboration", "Live", "Requests, approval and verified completion messages"],
                ["Gmail", "Collaboration", "Live", "Authorized email request and approval workflow"],
                ["Datadog", "Monitoring", "Roadmap", "Webhook intake and scoped API acknowledgement"],
                ["Azure", "Cloud operations", "Foundation", "Managed identity or scoped Entra application"],
                ["VMware", "Infrastructure", "Foundation", "Restricted vCenter service account"],
              ].map(([name, group, status, description]) => (
                <button key={name} onClick={() => setSection(name === "AWS" ? "AWS connection model" : name === "Datadog" ? "Datadog" : name === "SCCM / WSUS" ? "SCCM connector" : "Integration runbook")}>
                  <span className="integration-doc-icon"><Plug/></span><span><small>{group}</small><b>{name}</b><p>{description}</p></span><em>{status}</em>
                </button>
              ))}
            </div>
            <Callout title="Honest maturity labels">Live means working end to end. Demo is a validated demonstration flow. Foundation is partial implementation. Roadmap integrations are design-ready but not production connectors.</Callout>
          </>
        )}
        {section === "AWS connection model" && (
          <>
            <p className="docs-breadcrumb">Docs / Integrations / AWS / Connection model</p>
            <p className="eyebrow">AWS INTEGRATION · LIVE</p>
            <h2>How OpsAgent connects to AWS</h2>
            <p className="lead">Connect an AWS account from the OpsAgent Connections page using a restricted IAM access key. For production customer accounts, add a cross-account role and External ID so the stored key is used only to request temporary STS credentials.</p>
            <div className="doc-callout doc-callout-warning"><AlertTriangle/><div><strong>Never use the AWS root account</strong><p>Create a dedicated IAM identity named for OpsAgent, grant only the permissions required by your enabled workflows, and rotate or revoke it independently.</p></div></div>
            <h3>Choose an authentication model</h3>
            <div className="docs-comparison"><article><span>QUICK START · AVAILABLE NOW</span><h4>Restricted IAM access key</h4><p>Best for evaluation and a single account. OpsAgent encrypts the Access key ID and Secret access key in the tenant credential vault.</p><ul><li>Create a dedicated IAM user such as <code>OpsAgentLocal</code></li><li>Select <b>Third-party service</b> when AWS asks for the use case</li><li>Leave Role ARN and External ID empty</li></ul></article><article><span>PRODUCTION · RECOMMENDED</span><h4>Cross-account IAM role</h4><p>Best for customer environments. The base identity assumes the customer role and receives temporary STS credentials.</p><ul><li>Customer supplies a complete Role ARN</li><li>Use a unique, private External ID per customer</li><li>Apply least privilege and target tags in the customer account</li></ul></article></div>
            <h3>Quick setup from AWS Console</h3>
            <div className="aws-onboarding-steps"><article><b>01</b><span><strong>Create the IAM user</strong><p>AWS Console → IAM → Users → Create user. Use a dedicated name such as <code>OpsAgentLocal</code>; do not enable console access.</p></span></article><article><b>02</b><span><strong>Assign least privilege</strong><p>Attach a customer-managed policy containing only required EC2 discovery and approved operation permissions. Start read-only, then enable mutations deliberately.</p></span></article><article><b>03</b><span><strong>Create the access key</strong><p>Security credentials → Create access key → Third-party service. Copy both values immediately; AWS displays the secret only once.</p></span></article><article><b>04</b><span><strong>Connect in OpsAgent</strong><p>Connections → Amazon Web Services → Connect. Enter the key pair and the region containing your resources, then select Connect and synchronize.</p></span></article><article><b>05</b><span><strong>Verify inventory</strong><p>OpsAgent calls STS to identify the account, validates EC2 access and imports inventory. Confirm the returned account and region before enabling changes.</p></span></article></div>
            <h3>OpsAgent field reference</h3>
            <div className="docs-parameter-table"><div><b>Field</b><b>Required value</b></div><div><code>Connection name</code><span>A friendly OpsAgent label, for example <code>Acme Production AWS</code>. It does not need to match the IAM username.</span></div><div><code>AWS access key ID</code><span>The Access key ID generated by AWS, normally beginning with <code>AKIA</code>. Do not enter a user ARN here.</span></div><div><code>AWS secret access key</code><span>The secret displayed once when the access key is created. Never enter the AWS console password.</span></div><div><code>Primary AWS region</code><span>The region containing the resources to synchronize, for example <code>ap-south-1</code> or <code>us-east-2</code>.</span></div><div><code>Cross-account role ARN</code><span>Optional. When used, enter the complete value: <code>arn:aws:iam::123456789012:role/OpsAgentConnectorRole</code>.</span></div><div><code>External ID</code><span>Optional with access keys; required by policy for the recommended cross-account design. It is not the AWS account ID.</span></div></div>
            <Callout title="How validation works">OpsAgent encrypts the submitted credentials, calls AWS STS GetCallerIdentity, tests EC2 inventory access, and then synchronizes resources. Secret values are never returned to the browser after saving.</Callout>
            <h3>Component responsibilities</h3>
            <div className="aws-responsibility-grid">
              <article><Cloud/><b>CloudFormation</b><p>Creates and updates the connector IAM role and its least-privilege policies. It is an installer, not a monitoring agent.</p></article>
              <article><KeyRound/><b>Connector IAM role</b><p>Allows OpsAgent to discover AWS resources and, when enabled, request guarded EC2 and SSM operations using temporary credentials.</p></article>
              <article><Workflow/><b>Systems Manager</b><p>Routes approved documents and parameters to the exact managed Windows or Linux target and returns command status and output.</p></article>
              <article><Server/><b>SSM Agent</b><p>Runs on each server, connects outbound to AWS, executes the approved document and reports the result. It requires an EC2 instance role.</p></article>
              <article><ShieldCheck/><b>OpsAgent One</b><p>Applies tenant RBAC, resolves the target, requests approval, invokes the connector, verifies final state and records evidence.</p></article>
            </div>
            <h3>End-to-end request flow</h3>
            <div className="aws-connection-flow"><span><b>1</b>Operator request</span><ChevronRight/><span><b>2</b>Policy and approval</span><ChevronRight/><span><b>3</b>Assume connector role</span><ChevronRight/><span><b>4</b>AWS API or SSM</span><ChevronRight/><span><b>5</b>Verify and audit</span></div>
            <h3>Two IAM roles, two different purposes</h3>
            <div className="docs-comparison"><article><span>CONTROL PLANE</span><h4>OpsAgentConnectorRole</h4><p>Trusted by the OpsAgent principal and protected by the External ID. It grants discovery and optional guarded operations.</p><ul><li>Attached to: neither EC2 nor a person</li><li>Used by: OpsAgent backend</li><li>Credentials: temporary STS session</li></ul></article><article><span>SERVER</span><h4>EC2 instance role</h4><p>Attached to each managed Windows or Linux instance so its local SSM Agent can communicate with Systems Manager.</p><ul><li>Attached to: EC2 instance profile</li><li>Used by: local SSM Agent</li><li>Typical policy: AmazonSSMManagedInstanceCore</li></ul></article></div>
            <h3>CloudFormation parameters</h3>
            <div className="docs-parameter-table"><div><b>Parameter</b><b>Purpose</b></div><div><code>OpsAgentPrincipalArn</code><span>IAM user or role allowed to assume the connector role.</span></div><div><code>ExternalId</code><span>Private, customer-specific value that protects cross-account role assumption.</span></div><div><code>EnableGuardedOperations</code><span>Enables start, stop and reboot only for permitted, tagged EC2 instances.</span></div><div><code>EnableSsmOperations</code><span>Enables approved <code>OpsAgent-*</code> SSM documents on permitted, tagged instances.</span></div></div>
            <h3>Security controls</h3>
            <ul><li>Keep the External ID in the backend secret store; never place it in browser code or documentation screenshots.</li><li>Tag approved targets with <code>OpsAgentManaged=true</code>.</li><li>Allow only fixed <code>OpsAgent-*</code> SSM documents—never arbitrary shell commands.</li><li>Require human approval for state-changing operations.</li><li>Record requester, approver, target, parameters, command ID, output and verified final state.</li><li>Start with read-only access and validate operations on a non-production server.</li></ul>
            <h3>Credential lifecycle</h3>
            <ol><li>Create a replacement access key on the same restricted IAM user.</li><li>Update and verify the connection in OpsAgent before revoking the old key.</li><li>Deactivate the old key, monitor for errors, and then delete it.</li><li>Record the owner, reason, rotation date and validation result in the change record.</li></ol>
            <h3>Troubleshooting</h3>
            <div className="docs-troubleshoot"><div><b>Access key must begin with AKIA</b><p>You entered a user ARN or username. Create an IAM access key and copy its Access key ID.</p></div><div><b>InvalidClientTokenId</b><p>Confirm the key was copied completely, belongs to the intended AWS partition and has not been deactivated.</p></div><div><b>SignatureDoesNotMatch</b><p>The secret key is incorrect. AWS cannot display it again; create a replacement access key.</p></div><div><b>AccessDenied</b><p>The identity is valid but lacks STS, EC2 discovery or requested operation permissions. Review the IAM policy and target conditions.</p></div><div><b>No resources imported</b><p>Confirm the selected region. EC2 inventory is regional, so a valid connection can return zero resources in the wrong region.</p></div><div><b>Role cannot be assumed</b><p>Use the complete role ARN and ensure its trust policy permits the base identity with the exact External ID.</p></div></div>
            <Callout title="What you do not need">Do not create an API Gateway key or share a root credential, AWS console password, MFA code or ordinary IAM user ARN with OpsAgent.</Callout>
          </>
        )}
        {section === "Datadog" && (
          <>
            <p className="docs-breadcrumb">Docs / Integrations / Datadog</p>
            <div className="integration-title"><Activity/><div><p className="eyebrow">MONITORING INTEGRATION · GRAFANA · DATADOG</p><h2>Datadog</h2><p className="lead">Receive Datadog monitor events, acknowledge the incident through OpsAgent, run an approved investigation and return verified evidence to the incident channel.</p></div></div>
            <div className="doc-callout doc-callout-warning"><AlertTriangle/><div><strong>Connector status: not yet production-enabled</strong><p>This page defines the secure implementation contract. Do not enter Datadog credentials until the connector endpoint and secret storage are enabled.</p></div></div>
            <h3>How the integration works</h3>
            <div className="docs-flow"><span>Datadog monitor</span><ChevronRight/><span>Signed webhook</span><ChevronRight/><span>OpsAgent policy</span><ChevronRight/><span>Approved runbook</span><ChevronRight/><span>Slack / email result</span></div>
            <h3>Prerequisites</h3>
            <ul><li>OpsAgent organization administrator access.</li><li>A dedicated Datadog service account with only required monitor and event scopes.</li><li>An HTTPS webhook endpoint reachable from Datadog.</li><li>A customer secret manager for tokens and webhook signing secrets.</li><li>At least one allowlisted investigation runbook and notification channel.</li></ul>
            <h3>1. Create a dedicated identity</h3>
            <ol><li>Create a service account for OpsAgent; do not reuse a human administrator.</li><li>Grant only the API scopes required to read monitor context and post acknowledgement or comments.</li><li>Create a short-lived application credential and store it in AWS Secrets Manager, Azure Key Vault or the customer's approved vault.</li><li>Record the owner, purpose, expiry date and rotation schedule.</li></ol>
            <Callout title="Credential boundary">The browser and AI model must never receive the Datadog API key, application key or webhook signing secret. The customer connector retrieves secrets only at execution time.</Callout>
            <h3>2. Configure the Datadog webhook</h3>
            <ol><li>Create an OpsAgent webhook integration in Datadog.</li><li>Set the destination to the tenant-specific HTTPS event endpoint.</li><li>Add a signing secret or authorization header from the customer secret store.</li><li>Send monitor ID, event ID, status, title, tags, priority and event URL. Do not send credentials or unnecessary log content.</li><li>Limit routing to the monitors and environments approved for automation.</li></ol>
            <CodeBlock>{`POST /api/v1/integrations/datadog/events\nAuthorization: Bearer <webhook-secret>\nContent-Type: application/json\n\n{\n  "event_id": "$ID",\n  "monitor_id": "$ALERT_ID",\n  "status": "$ALERT_STATUS",\n  "title": "$ALERT_TITLE",\n  "tags": "$TAGS"\n}`}</CodeBlock>
            <h3>3. Map events to policy</h3>
            <ol><li>Map Datadog tags such as <code>env</code>, <code>service</code> and <code>team</code> to the OpsAgent organization and target.</li><li>Allow automatic acknowledgement and read-only diagnostics.</li><li>Require human approval for restart, scaling, patching or any state-changing action.</li><li>Reject unknown targets, missing signatures, expired timestamps and replayed event IDs.</li></ol>
            <h3>4. Validate safely</h3>
            <ol><li>Trigger a test monitor in a non-production environment.</li><li>Confirm signature validation, tenant mapping and duplicate-event protection.</li><li>Verify the acknowledgement appears in the configured Slack or email channel.</li><li>Approve a read-only investigation and confirm evidence is attached to the audit record.</li><li>Confirm no secret values appear in request logs, prompts, notifications or audit output.</li></ol>
            <h3>Troubleshooting</h3>
            <div className="docs-troubleshoot"><div><b>401 or 403</b><p>Check the webhook secret, API scopes, credential expiry and tenant mapping.</p></div><div><b>Event not received</b><p>Confirm HTTPS reachability, Datadog webhook delivery status and the monitor notification rule.</p></div><div><b>Duplicate incidents</b><p>Verify event-ID idempotency and recovery-event correlation.</p></div><div><b>Runbook blocked</b><p>Check target tags, organization policy, approval state and connector health.</p></div></div>
            <h3>Rotate or remove</h3>
            <ol><li>Create the replacement credential and update the secret version.</li><li>Run the validation test, then revoke the previous credential.</li><li>To disconnect, disable the webhook first, revoke tokens, remove stored secrets and retain the final audit record.</li></ol>
          </>
        )}
        {section === "Integration runbook" && (
          <>
            <p className="eyebrow">IMPLEMENTATION RUNBOOK</p>
            <h2>AWS, Windows, SCCM and patching</h2>
            <p className="lead">This is the repeatable setup used by OpsAgent One. Complete the stages in order and validate each trust boundary before enabling changes.</p>
            <div className="doc-steps">
              {[["1", "Connect AWS"], ["2", "Register Windows"], ["3", "Connect SCCM"], ["4", "Configure updates"], ["5", "Enable patch flow"]].map(([n, x]) => <div key={n}><b>{n}</b><span>{x}</span></div>)}
            </div>

            <h3>1. AWS identity and managed instances</h3>
            <ol>
              <li>Create a dedicated OpsAgent IAM identity for local evaluation, or a cross-account role with an External ID for customers.</li>
              <li>Grant EC2 discovery plus only the approved lifecycle operations. Restrict SSM execution to documents named <code>OpsAgent-*</code>.</li>
              <li>Attach <code>AmazonSSMManagedInstanceCore</code> to the EC2 instance role—not to the human/operator identity.</li>
              <li>Tag every allowed target <code>OpsAgentManaged=true</code>.</li>
              <li>Verify the operator with <code>aws sts get-caller-identity --profile opsagent</code>.</li>
            </ol>
            <Callout title="Two separate identities">The instance role lets the SSM Agent contact AWS. The OpsAgent operator identity discovers targets, sends approved commands and retrieves results.</Callout>

            <h3>2. Windows and Systems Manager</h3>
            <ol>
              <li>Confirm the Amazon SSM Agent is installed and running on every Windows server.</li>
              <li>Confirm DNS and outbound HTTPS access to the regional SSM endpoints.</li>
              <li>Verify all servers show <b>Online</b> in Systems Manager Fleet Manager.</li>
              <li>Publish fixed command documents such as <code>OpsAgent-install_windows_feature</code> and require an exact approval phrase before execution.</li>
              <li>Capture requestor, target, document, command ID, start time, final status, stdout, stderr and verification evidence.</li>
            </ol>
            <CodeBlock>{`Get-Service AmazonSSMAgent\nnslookup ssm.us-east-1.amazonaws.com\nRestart-Service AmazonSSMAgent`}</CodeBlock>

            <h3>3. SCCM read-only connector</h3>
            <ol>
              <li>Use the SCCM site server as an online, tagged SSM managed node.</li>
              <li>Install the Configuration Manager console and PowerShell module on that server.</li>
              <li>Publish <code>OpsAgent-sccm_inventory</code> and configure <code>SCCM_INSTANCE_ID</code>, <code>SCCM_REGION</code> and <code>SCCM_MODE=ssm</code>.</li>
              <li>Select <b>Sync SCCM</b> in OpsAgent and verify devices, collections, deployments and update groups.</li>
            </ol>

            <h3>4. Software Update Point and WSUS</h3>
            <ol>
              <li>Install WSUS services and add the SCCM <b>Software update point</b> role.</li>
              <li>Use ports 8530/8531, synchronize from Microsoft Update and enable a daily schedule.</li>
              <li>Select only required classifications: Critical Updates, Security Updates, Update Rollups and Updates.</li>
              <li>Select only managed products—for this environment, Windows Server 2022 and Windows Server 2025—and the required language.</li>
              <li>Run <b>Synchronize Software Updates</b>, monitor <code>SMS_WSUS_SYNC_MANAGER</code>, then confirm KB records appear in All Software Updates.</li>
            </ol>

            <h3>5. Patch rings and pipeline</h3>
            <ol>
              <li>Create <code>OPS-PATCH-TEST</code>, <code>OPS-PATCH-PILOT</code> and <code>OPS-PATCH-PRODUCTION</code> device collections.</li>
              <li>Use a direct membership rule for the single lab VM; leave Pilot and Production empty until approved devices exist.</li>
              <li>Create the monthly cycle in OpsAgent with release date, KBs, test/production windows, collection names, change ID and stakeholders.</li>
              <li>Progress through intake, baseline, lab test, change, notification and approval before deployment.</li>
              <li>Monitor compliant, pending, in-progress and failed devices; request post-patch validation and retain audit evidence.</li>
            </ol>
            <Callout title="Current automation boundary">OpsAgent currently provides SCCM inventory plus the persistent approval and audit pipeline. SCCM update-group, package and deployment mutation must be enabled through separate allowlisted SSM documents after the test deployment is validated.</Callout>

            <h3>Adding another company</h3>
            <p>Create a separate organization and customer connector. Use an AWS cross-account role, Azure workload identity, dedicated vCenter account, or local SCCM connector. Store credentials in the customer environment or encrypted secret store—never in the browser.</p>
          </>
        )}
        {section === "Architecture" && (
          <>
            <h2>Control plane and customer data plane</h2>
            <div className="architecture">
              <div>
                <Cloud />
                <strong>Control plane</strong>
                <span>React · FastAPI · PostgreSQL · policy · audit</span>
              </div>
              <i>Outbound TLS / mTLS</i>
              <div>
                <Server />
                <strong>Customer agent</strong>
                <span>AWS · Azure · VMware · Windows · Linux</span>
              </div>
            </div>
            <h3>Supported deployment patterns</h3>
            <ul>
              <li>
                <b>SaaS:</b> agents connect to your hosted control plane.
              </li>
              <li>
                <b>Private cloud:</b> deploy the full stack in the customer's
                cloud account.
              </li>
              <li>
                <b>Disconnected:</b> run the control plane and local model
                completely on-premises.
              </li>
            </ul>
          </>
        )}
        {section === "Control plane" && (
          <>
            <h2>Install the control plane</h2>
            <p>
              Evaluation runs the API and UI separately. Production should use
              containers, TLS and external PostgreSQL.
            </p>
            <h3>Python API</h3>
            <CodeBlock>{`cd server-downtime-agent\n.venv\\Scripts\\pip install -r requirements.txt\nset OPSAGENT_API_SECRET=<64-character-random-secret>\n.venv\\Scripts\\python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000`}</CodeBlock>
            <h3>React UI</h3>
            <CodeBlock>{`cd frontend\nnpm install\nnpm run build\nnpm run dev`}</CodeBlock>
          </>
        )}
        {section === "Customer agent" && (
          <>
            <h2>Install the customer agent</h2>
            <div className="doc-cards">
              {[
                [
                  "Windows service",
                  "Dedicated service account and certificate store",
                ],
                ["Linux service", "Dedicated user, systemd and sudo allowlist"],
                [
                  "Kubernetes",
                  "Namespace, service account, RBAC and network policy",
                ],
              ].map(([a, b]) => (
                <div key={a}>
                  <Terminal />
                  <strong>{a}</strong>
                  <span>{b}</span>
                </div>
              ))}
            </div>
            <h3>Registration workflow</h3>
            <ol>
              <li>Create a one-time registration token.</li>
              <li>Install the agent inside the customer network.</li>
              <li>Provide control-plane URL, organization ID and token.</li>
              <li>Exchange the token for an agent certificate.</li>
              <li>Approve the agent and assign environment policies.</li>
            </ol>
            <Callout title="Never share infrastructure passwords">
              Keep AWS, Azure, vCenter, Windows and Linux credentials in the
              customer's secret store.
            </Callout>
          </>
        )}
        {section === "Connect infrastructure" && (
          <>
            <h2>Connect infrastructure</h2>
            <div className="provider-docs">
              {[
                [
                  "AWS",
                  "IAM role: discovery first, approved lifecycle actions separately",
                ],
                [
                  "Azure",
                  "Managed identity or Entra application with scoped roles",
                ],
                [
                  "VMware",
                  "Dedicated vCenter service account restricted to managed folders",
                ],
                [
                  "Windows / SCCM",
                  "Managed service account and approved remoting",
                ],
                ["Linux", "SSH certificates or vault-managed keys"],
                [
                  "Hardware",
                  "Cisco UCS Manager, HPE OneView and Dell OpenManage",
                ],
              ].map(([a, b]) => (
                <div key={a}>
                  <CheckCircle2 />
                  <span>
                    <strong>{a}</strong>
                    <small>{b}</small>
                  </span>
                </div>
              ))}
            </div>
            <h3>Install the AWS connector</h3>
            <p>Use the packaged cross-account role. Operations are disabled by default and can be limited to resources tagged <code>OpsAgentManaged=true</code>.</p>
            <CodeBlock>{`$externalId = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
aws cloudformation deploy \`
  --region us-east-1 \`
  --stack-name opsagent-connector \`
  --template-file connectors/aws/cloudformation/opsagent-connector-role.yaml \`
  --capabilities CAPABILITY_NAMED_IAM \`
  --parameter-overrides OpsAgentPrincipalArn="<CONTROL_PLANE_ROLE_ARN>" ExternalId="$externalId" EnableGuardedOperations="false"`}</CodeBlock>
            <Callout title="Full customer handoff package">See connectors/aws/README.md for trust setup, FastAPI configuration, testing, guarded operations and production controls.</Callout>
          </>
        )}
        {section === "Choose an LLM" && (
          <>
            <h2>Choose the enterprise AI model</h2>
            <p>
              The organization selects its provider according to data residency,
              cost and infrastructure. Operations still pass through
              deterministic authorization and approval.
            </p>
            <div className="model-grid">
              {[
                ["OpenAI", "Managed cloud"],
                ["Azure OpenAI", "Azure enterprise"],
                ["AWS Bedrock", "AWS enterprise"],
                ["Ollama", "Local evaluation"],
                ["vLLM", "Private GPU inference"],
                ["Rules only", "No LLM required"],
              ].map(([a, b]) => (
                <div key={a}>
                  <Bot />
                  <strong>{a}</strong>
                  <span>{b}</span>
                </div>
              ))}
            </div>
            <CodeBlock>{`MODEL_PROVIDER=ollama\nMODEL_NAME=<approved-model>\nMODEL_BASE_URL=http://model-host:11434\nMODEL_API_KEY=<secret-if-required>`}</CodeBlock>
          </>
        )}
        {section === "SCCM connector" && (
          <>
            <p className="eyebrow">ENDPOINT MANAGEMENT</p>
            <h2>Connect Microsoft Configuration Manager</h2>
            <p className="lead">OpsAgent collects SCCM inventory through a fixed read-only Systems Manager document on the site server. No SCCM credential or arbitrary PowerShell is accepted from the browser.</p>
            <h3>Connection path</h3>
            <div className="architecture"><div><Bot/><strong>OpsAgent API</strong><span>Authenticated request and audit</span></div><i>AWS SSM Run Command</i><div><FaMicrosoft/><strong>OPSAGENT-SCCM01</strong><span>Configuration Manager PowerShell provider · site OPS</span></div></div>
            <h3>Prerequisites</h3>
            <ol><li>The SCCM server is an online SSM managed node.</li><li>The instance is tagged <code>OpsAgentManaged=true</code>.</li><li>The Configuration Manager console and PowerShell module are installed.</li><li><code>OpsAgent-sccm_inventory</code> exists as an SSM Command document.</li><li>The API is configured with the SCCM instance ID and region.</li></ol>
            <h3>Deploy the inventory document</h3>
            <CodeBlock>{`aws ssm create-document \
  --name "OpsAgent-sccm_inventory" \
  --document-type "Command" \
  --document-format "JSON" \
  --content "file://connectors/aws/ssm/sccm-inventory.json" \
  --region us-east-1 \
  --profile opsagent`}</CodeBlock>
            <Callout title="Safe by design">Inventory is read-only. Patch deployments and client actions must use separate allowlisted documents with explicit approval and verification.</Callout>
          </>
        )}
        {section === "Security" && (
          <>
            <h2>Secure every operation</h2>
            <div className="security-flow">
              {[
                "Authenticate user",
                "Authorize role and scope",
                "Preview exact impact",
                "Approve exact request",
                "Execute inside customer agent",
                "Verify resulting state",
                "Write immutable audit",
              ].map((x, i) => (
                <div key={x}>
                  <b>{i + 1}</b>
                  <span>{x}</span>
                </div>
              ))}
            </div>
          </>
        )}
        {section === "Production checklist" && (
          <>
            <h2>Production readiness</h2>
            {[
              "TLS for UI, API and agents",
              "Persistent API secret in a secret manager",
              "PostgreSQL HA, encryption and backups",
              "Enterprise SSO and MFA",
              "Tenant-scoped RBAC",
              "Agent certificate rotation",
              "Durable queues and idempotency",
              "Central logs, metrics and tracing",
              "Rollback and disaster-recovery testing",
              "Security scanning and penetration testing",
            ].map((x) => (
              <label className="check-item" key={x}>
                <input type="checkbox" />
                {x}
              </label>
            ))}
          </>
        )}
      </article>
      {section !== "Documentation home" && <aside className="docs-page-rail">
        <label><span>LANGUAGE</span><select aria-label="Documentation language"><option>English</option></select></label>
        <label><span>DEPLOYMENT</span><select aria-label="Deployment model"><option>Enterprise</option><option>Customer-managed</option></select></label>
        <div className="docs-rail-actions"><button onClick={() => navigator.clipboard.writeText(`${window.location.href.split("#")[0]}#docs-${section.toLowerCase().replaceAll(" ", "-")}`)}><Copy/> Copy link</button></div>
        <h3>ON THIS PAGE</h3>
        <nav><a href="#overview">Overview</a><a href="#prerequisites">Prerequisites</a><a href="#configuration">Configuration</a><a href="#security">Security controls</a><a href="#validation">Validation</a><a href="#troubleshooting">Troubleshooting</a></nav>
        <button className="docs-floating-ai" onClick={() => openSection("Overview")}><Sparkles/> Ask OpsAgent</button>
      </aside>}
      </div>
    </section>
    </div>
  );
}
function Callout({ title, children }: { title: string; children: string }) {
  return (
    <div className="doc-callout">
      <KeyRound />
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
    </div>
  );
}

type ServiceDeskTicket = {
  id: string;
  requester: string;
  request: string;
  status: "Awaiting connector" | "Pending approval" | "Guidance provided";
};

function ServiceDeskWorkspace() {
  const [question, setQuestion] = useState("");
  const [requester, setRequester] = useState("");
  const [requestType, setRequestType] = useState("Password reset");
  const [details, setDetails] = useState("");
  const [verified, setVerified] = useState(false);
  const [tickets, setTickets] = useState<ServiceDeskTicket[]>([]);
  const [callState, setCallState] = useState<"ready" | "connected" | "transferring" | "engineer">("ready");
  const [muted, setMuted] = useState(false);
  const [callSeconds, setCallSeconds] = useState(0);
  const [callTranscript, setCallTranscript] = useState<string[]>([]);

  useEffect(() => {
    if (callState !== "connected") return;
    const timer = window.setInterval(() => setCallSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [callState]);

  const startCall = () => {
    setCallState("connected");
    setCallSeconds(0);
    setMuted(false);
    setCallTranscript([
      "Agent: Welcome to the IT Service Desk. Please describe the problem you are experiencing.",
      "Agent: I will guide you through safe troubleshooting and confirm the result before closing the call.",
    ]);
  };
  const transferCall = () => {
    const id = `SD-${String(Date.now()).slice(-6)}`;
    setCallState("transferring");
    setTickets((current) => [{ id, requester: "Voice caller", request: "Engineer call handoff", status: "Pending approval" }, ...current]);
    setCallTranscript((current) => [...current, `Agent: I could not safely resolve this issue. I created ${id} and am transferring you to an engineer with the transcript and troubleshooting context.`]);
    window.setTimeout(() => {
      setCallState("engineer");
      setCallTranscript((current) => [...current, "System: Engineer handoff prepared. A live telephony connector is required to bridge the call."]);
    }, 900);
  };
  const endCall = () => {
    setCallState("ready");
    setMuted(false);
    setCallSeconds(0);
  };

  const answer = (value: string) => {
    const normalized = value.toLowerCase();
    if (normalized.includes("password")) return "I can prepare a password-reset request. First verify the employee through an approved MFA method. The agent will never ask for, display, or store a password.";
    if (normalized.includes("unlock") || normalized.includes("locked")) return "I can check the account-lock state after Entra ID or Active Directory is connected. Unlocking will require verified identity and will be recorded in the audit trail.";
    if (normalized.includes("vpn")) return "Check network access, system time, VPN client status, and MFA first. I can open a support ticket with those diagnostics if the issue continues.";
    if (normalized.includes("mfa")) return "MFA reset is a privileged action. I can collect the request, require identity verification, route approval, and execute only through the configured identity connector.";
    return "I can help with that request. I’ll provide safe guidance now, or create a service request and route it to the correct support team when an ITSM connector is available.";
  };
  const sendQuestion = (event: FormEvent) => {
    event.preventDefault();
    const value = question.trim();
    if (!value) return;
    setCallTranscript((current) => [...current, `Caller: ${value}`, `Agent: ${answer(value)}`]);
    setQuestion("");
  };
  const createRequest = (event: FormEvent) => {
    event.preventDefault();
    if (!requester.trim() || !details.trim()) return;
    const sensitive = ["Password reset", "Account unlock", "MFA reset"].includes(requestType);
    setTickets((current) => [{
      id: `SD-${String(Date.now()).slice(-6)}`,
      requester: requester.trim(),
      request: requestType,
      status: sensitive ? "Awaiting connector" : "Guidance provided",
    }, ...current]);
    setCallTranscript((current) => [...current, sensitive
      ? `Agent: ${requestType} request prepared for ${requester.trim()}. No account change was executed because an identity connector is not configured.`
      : `Agent: Support request recorded for ${requester.trim()}. Guidance is ready for review.`]);
    setDetails("");
  };
  const sensitiveRequest = ["Password reset", "Account unlock", "MFA reset"].includes(requestType);
  return <section className="product-page service-desk">
    <div className="page-lead desk-command-lead"><div><span className="badge">AI SERVICE DESK · VOICE OPERATIONS</span><h2>Autonomous support. Human escalation when needed.</h2><p>Answer the enterprise support number, verify the caller, resolve approved requests and warm-transfer unresolved calls with complete context.</p></div><div className="service-desk-actions"><span className="service-desk-status"><i/>Setup required</span><button className="secondary-action"><Cable/>Configure voice channel</button></div></div>
    <div className="service-desk-metrics desk-live-metrics"><article><span>Support number</span><strong>Not assigned</strong><small>Teams Phone · Twilio · Azure ACS</small></article><article><span>Calls waiting</span><strong>0</strong><small>No active queue</small></article><article><span>AI resolution rate</span><strong>—</strong><small>Available after first calls</small></article><article><span>Engineers available</span><strong>0</strong><small>Connect contact-center routing</small></article></div>
    <article className="service-desk-call enterprise-call-console"><header><div><span>LIVE INTERACTION</span><h3>{callState === "ready" ? "Voice channel is not connected" : "Employee support call in progress"}</h3><p>{callState === "ready" ? "Assign a published support number to let the AI agent answer real incoming calls." : "AI Agent · English · identity verification required"}</p></div><span className={`call-state ${callState}`}><i/>{callState === "ready" ? "Offline" : callState === "engineer" ? "Handoff ready" : callState}</span></header><div className="enterprise-call-grid"><section className="caller-identity"><div className="caller-avatar"><Phone/></div><div><span>CALLER</span><strong>{callState === "ready" ? "Waiting for inbound call" : "+91 ••••• ••482"}</strong><small>{callState === "ready" ? "No telephony provider configured" : "Employee identity not verified"}</small></div><div className="call-controls">{callState === "ready" ? <button className="primary-action" onClick={startCall}><Play/>Run interaction preview</button> : <><button className={muted?"active":""} onClick={()=>setMuted((value)=>!value)}><Mic/>{muted?"Unmute":"Mute"}</button><button className="end-call" onClick={endCall}>End</button></>}</div></section><section className="call-transcript"><div><b>Live conversation</b><span>{callState === "ready" ? "00:00" : `${String(Math.floor(callSeconds / 60)).padStart(2,"0")}:${String(callSeconds % 60).padStart(2,"0")}`}</span></div>{callTranscript.length?callTranscript.map((line,index)=><p key={index}>{line}</p>):<p className="transcript-empty">The caller and AI transcript will appear here in real time.</p>}<form className="desk-simulate-utterance" onSubmit={sendQuestion}><input value={question} onChange={(event)=>setQuestion(event.target.value)} placeholder="Preview a caller question…"/><button disabled={!question.trim()}><Send/></button></form></section><aside className="resolution-rail"><span>RESOLUTION WORKFLOW</span><ol><li className={callState!=="ready"?"active":""}><b>1</b><div><strong>Identify caller</strong><small>Phone match + approved MFA</small></div></li><li><b>2</b><div><strong>Diagnose request</strong><small>Knowledge + endpoint context</small></div></li><li><b>3</b><div><strong>Execute safely</strong><small>Policy-approved tools only</small></div></li><li><b>4</b><div><strong>Confirm outcome</strong><small>User confirmation + audit</small></div></li></ol><button className="handoff-action" onClick={transferCall} disabled={callState!=="connected"}><PhoneForwarded/>Warm transfer to engineer</button><small>Transcript, identity result, diagnostics and ticket follow the call.</small></aside></div></article>
    <div className="service-desk-layout">
      <article className="service-desk-panel desk-routing"><header><div><span>CALL ROUTING</span><h3>Enterprise voice and escalation</h3></div><Workflow/></header><div className="routing-options"><section><Phone/><div><strong>Inbound support number</strong><span>Acquire or port a number through Teams Phone, Twilio or Azure Communication Services.</span></div><b>Required</b></section><section><Bot/><div><strong>AI voice agent</strong><span>Speech, service-desk knowledge, identity verification and allowlisted tools.</span></div><b>Ready</b></section><section><Users/><div><strong>Engineer queue</strong><span>Skills-based routing, presence, business hours and overflow destination.</span></div><b>Required</b></section><section><Database/><div><strong>ITSM record</strong><span>ServiceNow or Jira ticket, call recording policy, transcript and audit evidence.</span></div><b>Required</b></section></div></article>
      <article className="service-desk-panel"><header><div><span>GUARDED REQUEST</span><h3>Create a service request</h3></div><KeyRound/></header><form className="service-request-form" onSubmit={createRequest}><label>Employee email or ID<input value={requester} onChange={(event)=>setRequester(event.target.value)} placeholder="employee@company.com"/></label><label>Request type<select value={requestType} onChange={(event)=>{setRequestType(event.target.value);setVerified(false);}}><option>Password reset</option><option>Account unlock</option><option>MFA reset</option><option>VPN issue</option><option>Email issue</option><option>Software request</option><option>Other IT question</option></select></label><label>Issue details<textarea value={details} onChange={(event)=>setDetails(event.target.value)} placeholder="Describe the issue without including passwords or authentication codes."/></label>{sensitiveRequest&&<label><span><input type="checkbox" checked={verified} onChange={(event)=>setVerified(event.target.checked)}/> Employee identity verified through an approved method</span></label>}<div className="guardrail"><ShieldCheck/><span>Passwords and MFA codes are never collected. Sensitive actions remain blocked until Entra ID/Active Directory, approval and audit connectors are configured.</span></div><button className="primary-action" disabled={!requester.trim()||!details.trim()||(sensitiveRequest&&!verified)}>Prepare secure request</button></form></article>
      <article className="service-desk-panel service-desk-queue"><header><div><span>REQUEST QUEUE</span><h3>Service desk activity</h3></div><span>{tickets.length} REQUESTS</span></header>{tickets.length?tickets.map((ticket)=><div className="desk-ticket" key={ticket.id}><b>{ticket.id}</b><span>{ticket.requester}</span><strong>{ticket.request}</strong><em className={ticket.status==="Guidance provided"?"ready":""}>{ticket.status}</em></div>):<div className="desk-empty">No requests yet. Ask a question or prepare a guarded service request above.</div>}</article>
    </div>
  </section>;
}

function AgentWorkspace({ health, onNavigate }: { health: Health[]; onNavigate?: (page:string)=>void }) {
  const componentHealthy = (...terms:string[]) => health.some((item) => terms.some((term) => item.Component.toLowerCase().includes(term)) && item.Status === "Healthy");
  const isReady = (status:string) => ["Operational", "Available", "Policy active"].includes(status);
  const agents = [
    { name: "Infrastructure Agent", role: "Discovers and operates cloud and virtualization targets through approved connectors.", icon: Cloud, tone: "cyan", status: componentHealthy("aws","inventory") ? "Operational" : "Check connectors", workspace:"AWS operations", connectors:["AWS live","Azure foundation","VMware foundation"], tools:["Inventory","Lifecycle","Storage","Networks"] },
    { name: "Hardware Monitoring Agent", role: "Inspects Cisco, Dell and HPE chassis, blades and components; diagnoses faults, reports daily and prepares approval-gated ITSM tickets.", icon: ServerCog, tone: "green", status: "Connector required", workspace:"Hardware monitoring", connectors:["Cisco CIMC / Intersight","Dell iDRAC / OME","HPE iLO / OneView"], tools:["Inspect","Diagnose","Report","Escalate"] },
    { name: "Patch Management Agent", role: "Coordinates endpoint inventory, update rings, approvals and compliance evidence.", icon: MonitorCog, tone: "purple", status: componentHealthy("sccm") ? "Operational" : "Connector required", workspace:"SCCM operations", connectors:["SCCM inventory live","WSUS connected","Intune roadmap"], tools:["KB intake","Test rings","Approval","Compliance"] },
    { name: "Security Agent", role: "Applies RBAC, target restrictions and human approval before infrastructure changes.", icon: ShieldCheck, tone: "blue", status: "Policy active", workspace:"Account & access", connectors:["Tenant RBAC","Approval policy","Audit database"], tools:["Authorize","Approve","Verify","Audit"] },
    { name: "Monitoring Agent", role: "Receives operational signals, correlates incidents and coordinates human response.", icon: Activity, tone: "green", status: componentHealthy("slack","grafana","email") ? "Operational" : "Check channels", workspace:"Slack alerts", connectors:["Grafana webhook","Slack live","Gmail live"], tools:["Receive","Correlate","Acknowledge","Notify"] },
    { name: "Knowledge Agent", role: "Provides runbooks, architecture guidance and enterprise operational context.", icon: BookOpen, tone: "amber", status: "Available", workspace:"Documentation", connectors:["Runbook catalog","Public docs","Inventory context"], tools:["Search","Explain","Plan","Guide"] },
    { name: "Service Desk Agent", role: "Answers employee IT questions and coordinates identity-verified password, account, MFA and support workflows.", icon: MessageSquare, tone: "cyan", status: "Connector required", workspace:"Service desk agent", connectors:["Entra ID / Active Directory","ServiceNow / Jira Service Management","Email / Teams"], tools:["Assist","Verify","Request","Escalate"] },
  ];
  return <section className="product-page agent-center">
    <div className="page-lead"><div><span className="badge">AGENT ORCHESTRATION</span><h2>Domain agents connected to real operations</h2><p>Each agent has a defined responsibility, connector scope and allowlisted toolset. OpsAgent coordinates policy, approval, execution and evidence across them.</p></div><button className="primary-action" onClick={()=>onNavigate?.("Connections")}><Cable /> Manage connectors</button></div>
    <div className="agent-stats"><div><span>Domain agents</span><strong>{agents.length}</strong></div><div><span>Healthy services</span><strong>{health.filter(x => x.Status === "Healthy").length}<small> / {health.length}</small></strong></div><div><span>Approval control</span><strong className="small-value">Required</strong></div><div><span>Execution mode</span><strong className="small-value">Guarded</strong></div></div>
    <section className="orchestration-registry">
      <header><div><span>AGENT REGISTRY</span><h3>Operational agents</h3><p>See what each agent controls, whether it is ready, and where to manage it.</p></div><b><i/> Policy connected</b></header>
      <div className="orchestration-flow" aria-label="Guarded execution lifecycle"><span><ShieldCheck/>Request verified</span><ChevronRight/><span><Users/>Approval</span><ChevronRight/><span><Workflow/>Execute</span><ChevronRight/><span><CheckCircle2/>Evidence recorded</span></div>
      <div className="agent-registry-head"><span>Agent</span><span>Readiness</span><span>Connected scope</span><span>Approved capabilities</span><span>Workspace</span></div>
      <div className="agent-registry-body">{agents.map(({name,role,icon:Icon,tone,status,workspace,connectors,tools}) => <article className="agent-registry-row" key={name}>
        <div className="agent-registry-identity"><span className={`agent-symbol ${tone}`}><Icon /></span><div><strong>{name}</strong><p>{role}</p></div></div>
        <span className={`agent-runtime ${isReady(status)?"ready":"attention"}`}><i />{status}</span>
        <div className="agent-connector-list">{connectors.map((item,index)=><span key={item} className={index===0&&isReady(status)?"connected":""}><i/>{item}</span>)}</div>
        <div className="agent-capability-list">{tools.map((item)=><span key={item}>{item}</span>)}</div>
        <button className="agent-open-action" onClick={()=>onNavigate?.(workspace)}>Open <ChevronRight /></button>
      </article>)}</div>
    </section>
  </section>;
}

function OperationsAnalyticsWorkspace({summary,servers}:{summary:Summary|null;servers:Machine[]}) {
  const [report, setReport] = useState("Operational overview");
  const [scope, setScope] = useState("All infrastructure");
  const [period, setPeriod] = useState("Last 24 hours");
  if (!summary) return <div className="skeleton">Loading operations analytics…</div>;
  const scopedServers = servers.filter((server) => {
    if (scope === "All infrastructure") return true;
    const provider = String(server.vm_type || "unknown").toLowerCase();
    if (scope === "On-premises") return ["onprem","on-prem","physical","vmware"].includes(provider);
    return provider === scope.toLowerCase();
  });
  const monitored = scopedServers.filter((server) => server.monitoring_service).length;
  const poweredOn = scopedServers.filter((server) => ["running","active","on","poweredon","powered on"].includes(String(server.status).toLowerCase())).length;
  const poweredOff = scopedServers.filter((server) => ["stopped","deallocated","off","poweredoff","powered off"].includes(String(server.status).toLowerCase())).length;
  const monitoringCoverage = scopedServers.length ? Math.round(monitored / scopedServers.length * 100) : 0;
  const providerRows = ["aws","azure","vmware","onprem","physical"].map((provider) => {
    const assets = scopedServers.filter((server) => String(server.vm_type).toLowerCase() === provider);
    return { Provider: provider === "onprem" ? "On-premises" : provider.toUpperCase(), Assets: assets.length, "Powered on": assets.filter((server)=>["running","active","on","poweredon","powered on"].includes(String(server.status).toLowerCase())).length, Monitored: assets.filter((server)=>server.monitoring_service).length };
  }).filter((row)=>Number(row.Assets)>0);
  const exportReport = () => {
    const payload = {generated_at:new Date().toISOString(),report,scope,period,assets:scopedServers.length,powered_on:poweredOn,powered_off:poweredOff,monitoring_coverage:monitoringCoverage,provider_summary:providerRows};
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:"application/json"}));
    const link=document.createElement("a"); link.href=url; link.download="opsagent-operations-analytics.json"; link.click(); URL.revokeObjectURL(url);
  };
  return <section className="product-page analytics-page operations-analytics-page">
    <div className="page-lead"><div><span className="badge">OPERATIONS ANALYTICS</span><h2>Infrastructure coverage and reporting</h2><p>Measure infrastructure utilization, monitoring coverage and operational trends across every managed domain.</p></div><button className="secondary-action" onClick={exportReport}><Download/> Export report</button></div>
    <div className="analytics-controls"><label>Report<select value={report} onChange={(event)=>setReport(event.target.value)}><option>Operational overview</option><option>Inventory coverage</option></select></label><label>Infrastructure scope<select value={scope} onChange={(event)=>setScope(event.target.value)}><option>All infrastructure</option><option>AWS</option><option>Azure</option><option>VMware</option><option>On-premises</option></select></label><label>Time period<select value={period} onChange={(event)=>setPeriod(event.target.value)}><option>Last 24 hours</option><option>Last 7 days</option><option>Last 30 days</option><option>Last 90 days</option></select></label></div>
    <div className="analytics-kpis"><article><span>Managed domains</span><strong>{providerRows.length}</strong><small>Infrastructure providers in scope</small></article><article><span>Infrastructure assets</span><strong>{scopedServers.length}</strong><small>{poweredOn} currently powered on</small></article><article><span>Monitoring coverage</span><strong>{monitoringCoverage}%</strong><small>{monitored} of {scopedServers.length} assets assigned</small></article><article><span>Powered off</span><strong>{poweredOff}</strong><small>Review decommission inventory</small></article></div>
    {(report === "Operational overview" || report === "Inventory coverage") && <SimpleTable title={`${scope} coverage · ${period}`} rows={providerRows}/>} 
  </section>;
}

function AnalyticsWorkspace({summary,servers,health}:{summary:Summary|null;servers:Machine[];health:Health[]}) {
  if (!summary) return <div className="skeleton">Loading analytics…</div>;
  const score = health.length ? Math.round(health.filter(x => x.Status === "Healthy").length / health.length * 100) : 0;
  const compliance = summary.total ? Math.round(servers.filter(s => s.monitoring_service).length / summary.total * 100) : 0;
  const chart = [42,48,45,57,62,58,71,69,78,82,80,Math.max(84,score)];
  return <section className="product-page analytics-page"><div className="page-lead"><div><span className="badge">ENTERPRISE ANALYTICS</span><h2>Operational posture and trends</h2><p>Turn infrastructure telemetry into measurable health, compliance and risk outcomes.</p></div><button className="secondary-action">Export report</button></div><div className="analytics-kpis"><article><span>Security score</span><strong>{score}</strong><small>Healthy control signals</small></article><article><span>Monitoring coverage</span><strong>{compliance}%</strong><small>Inventory with assigned monitoring</small></article><article><span>Patch compliance</span><strong>—</strong><small>Connect SCCM or Intune</small></article><article><span>Cloud utilization</span><strong>{summary.total ? Math.round(summary.powered_on/summary.total*100) : 0}%</strong><small>Powered-on estate</small></article></div><div className="analytics-grid"><article className="intel-panel trend-card"><div className="intel-title"><div><span>12-PERIOD TREND</span><h3>Enterprise health score</h3></div><small>Live + historical signals</small></div><div className="mini-chart">{chart.map((v,i)=><i key={i} style={{height:`${v}%`}}><span>{v}</span></i>)}</div><div className="chart-axis"><span>Earlier</span><span>Current</span></div></article><article className="intel-panel posture-card"><div className="intel-title"><div><span>POSTURE</span><h3>Infrastructure coverage</h3></div></div><div className="score-ring" style={{"--score":`${score * 3.6}deg`} as React.CSSProperties}><div><strong>{score}%</strong><span>Healthy</span></div></div><div className="posture-legend"><span><i className="good"/>Healthy {health.filter(x=>x.Status==="Healthy").length}</span><span><i className="bad"/>Needs attention {health.filter(x=>x.Status!=="Healthy").length}</span></div></article></div></section>;
}

function ComingSoon({ title }: { title: string }) {
  return (
    <section className="empty">
      <OpsLogo />
      <h2>{title}</h2>
      <p>
        This workspace is connected to the enterprise shell and will be migrated
        from the operational Streamlit application next.
      </p>
    </section>
  );
}
export default App;
