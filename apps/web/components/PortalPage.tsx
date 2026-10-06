import {notFound} from "next/navigation";import {Suspense} from "react";import { accessUnavailable } from "./AccessUnavailable";import AgentApplicationsSection from "./AgentApplicationsSection";import ApplicationFilterBar from "./ApplicationFilterBar";import AgentDashboardPanel,{AgentDashboardSkeleton} from "./AgentDashboardPanel";import AgentDocumentsSection from "./AgentDocumentsSection";import AgentNotificationsSection from "./AgentNotificationsSection";import AgentPerformanceSection from "./AgentPerformanceSection";import AgentReportsPanel from "./AgentReportsPanel";import AgentStudentsSection from "./AgentStudentsSection";import AgentTasksSection from "./AgentTasksSection";import AgentUniversitiesPanel from "./AgentUniversitiesPanel";import PortalShell from "./PortalShell";import PortalSection from "./PortalSection";import RefreshOnHistoryNav from "./RefreshOnHistoryNav";import TeacherWorkspaceActions from "./TeacherWorkspaceActions";import WorkflowPanel from "./WorkflowPanel";import {ApiError,serverApi} from "@/lib/api";import {AGENT_NOTIFICATIONS_HREF,agentNavFor,PORTAL_NAV,withBadge} from "@/lib/navigation";import type {NotificationItem} from "./SchoolNotificationList";import type {PortalPayload,User} from "@/lib/types";
const labels:Record<string,string>={"it/student":"IT Student","it/trainer":"Trainer","it/placement":"Placement Team","it/hr":"HR / Employer","it/admin":"IT Administrator","it/counselor":"Counselor","overseas/student":"Overseas Student","overseas/counselor":"Counselor","overseas/university":"University Representative","overseas/agent":"Education Agent","overseas/admin":"Overseas Administrator"};
export default async function PortalPage({division,role,section,query}:{division:"it"|"overseas";role:string;section:string;query?:Record<string,string|string[]|undefined>}){const key=`${division}/${role}`;const nav=PORTAL_NAV[key]||[];if(!nav.some(item=>item.href===`/${division}/${role}/${section}`))notFound();// AGN-008 QA8-09: the agency Applications page reads its own API (AgentApplicationsSection). The portal payload is still fetched
// as the page's role/approval gate (403 for a wrong role or a pending/rejected agent); only its 404 "Workspace not found" is held
// back there, and only a Super Admin then gets the section (its note) -- anyone else still gets the access-unavailable card.
const agentApplications=key==="overseas/agent"&&section==="applications";
// AGN-009: the agency Documents page reads its own API too (AgentDocumentsSection), behind the same portal-payload gate.
const agentDocuments=key==="overseas/agent"&&section==="documents";
// AGN-016 browser QA16-01: the agency Tasks page also reads its own API, so a Super Admin gets its note the same way.
const agentTasks=key==="overseas/agent"&&section==="tasks";
// AGN-017 (DEC-SCOPE-059 N7/N8): the agency Notifications page reads the existing list (fetched beside the payload, so no extra round
// trip); every agency page carries the unread count on the Notifications nav item. A failed count only drops the badge; a failed list
// shows the section-unavailable state; a 401 from it is an expired session, so the access-unavailable card.
const agentNotifications=key==="overseas/agent"&&section==="notifications";
// AGN-019 (DEC-SCOPE-066 P7): Staff Performance reads its own API (AgentPerformanceSection), behind the same portal-payload gate.
const agentPerformance=key==="overseas/agent"&&section==="performance";
// AGN-023 (DEC-SCOPE-090 H11): only agency/counselor travel to the API; a refused filter (422) falls back to the unfiltered list with
// the message, instead of the access-unavailable card.
const filterParams=new URLSearchParams(Object.entries(query||{}).filter((e):e is [string,string]=>(e[0]==="agency"||e[0]==="counselor")&&typeof e[1]==="string"));const filterQuery=filterParams.toString();let filterError:string|null=null;
const portalUrl=`/api/v1/portal/${division}/${role}/${section}`;
let user:User;let data:PortalPayload|null;let unread:number|null;let notices:NotificationItem[]|null;try{[user,data,unread,notices]=await Promise.all([serverApi<User>("/api/v1/auth/me"),serverApi<PortalPayload>(filterQuery?`${portalUrl}?${filterQuery}`:portalUrl).catch((e)=>{if(filterQuery&&e instanceof ApiError&&e.status===422){filterError=e.message;return serverApi<PortalPayload>(portalUrl)}if((agentApplications||agentDocuments||agentTasks||agentNotifications||agentPerformance)&&e instanceof ApiError&&e.status===404)return null;throw e}),key==="overseas/agent"?serverApi<{unread:number}>("/api/v1/workflows/notifications/unread-count").then((r)=>r.unread,()=>null):null,agentNotifications?serverApi<NotificationItem[]>("/api/v1/workflows/notifications").catch((e)=>{if(e instanceof ApiError&&e.status===401)throw e;return null}):null])}catch(e){return accessUnavailable(e, `/${division}/login`)}
if(!data&&user.role!=="super_admin")return accessUnavailable(new ApiError("Workspace not found",404), `/${division}/login`);const teacherWorkspace=division==="it"&&role==="trainer";
// AGN-002: an agency's staff see no Team/Commissions links; the full `nav` above still admits a typed URL, so the server's 403 card shows.
const agent=key==="overseas/agent";
// AGN-004 browser QA-01/02: the agency Students page leads with every student (with or without a login), full width; the
// AGT-002 roster below is retitled as what it is -- application status of the students who have a login.
// AGN-007 (DEC-SCOPE-049): the agency's own universities -- the panel is the page (the payload is header-only).
// AGN-008: the agency Applications page is the applications panel (list, detail, filters); the generic table is replaced there only.
// AGN-016 (DEC-SCOPE-053): the agency Tasks page -- the payload is header-only (the Universities precedent) and still gates the page.
const main=agentApplications?<AgentApplicationsSection user={user}/>:agentDocuments?<AgentDocumentsSection user={user}/>:agentTasks?<AgentTasksSection user={user}/>:agentNotifications?<AgentNotificationsSection user={user} items={notices}/>:agentPerformance?<AgentPerformanceSection user={user}/>:!data?null:agent&&section==="students"?<>
<AgentStudentsSection user={user}/>
<PortalSection data={{...data,title:"Application status",subtitle:"Students who have a login, with each one's current application (AGT-002)."}}/>
</>:agent&&section==="universities"?<AgentUniversitiesPanel memberRole={user.agent_member_role}/>
// AGN-018 (DEC-SCOPE-062): agency members get the KPI board under the title (it reads its own endpoint and streams in, so the title
// and table render at once); the payload stays the page's gate, and its metric tiles are dropped so nothing shows twice.
:agent&&section==="dashboard"&&user.role==="agent"?<PortalSection data={{...data,metrics:[]}} lead={<Suspense fallback={<AgentDashboardSkeleton/>}><AgentDashboardPanel/></Suspense>}/>
// AGN-020 (DEC-SCOPE-067 R8): agency members get the tabbed reports (the Universities precedent: the panel is the page). The payload
// is still the page's gate -- staff without Reports get its 403 card above -- and its old summary table is no longer shown.
:agent&&section==="reports"&&user.role==="agent"?<AgentReportsPanel memberRole={user.agent_member_role}/>
// AGN-023 (DEC-SCOPE-090 H11): the overseas Admin's and counselor's Students/Applications lists lead with the filter bar.
:data.filters&&(key==="overseas/admin"||key==="overseas/counselor")?<PortalSection data={data} lead={<ApplicationFilterBar filters={data.filters} error={filterError}/>} emptyText={data.filters.agency||data.filters.counselor?"No applications match these filters":undefined}/>
:<PortalSection data={data}/>;
return <PortalShell nav={agent?withBadge(agentNavFor(nav,user.agent_member_role,user.agent_permissions),AGENT_NOTIFICATIONS_HREF,user.role==="agent"?unread:null):nav} roleLabel={agent&&user.agent_member_role==="staff"?"Agency Staff":labels[key]||role} userName={user.full_name} studentCode={role==="student"?user.student_code:null}>{/* AGN-003 browser QA-07: Back/Forward re-asks the server, so revoked permissions apply. */}{agent&&<RefreshOnHistoryNav/>}{main}{teacherWorkspace?<TeacherWorkspaceActions section={section}/>:agentNotifications?null:<WorkflowPanel user={user} section={section}/>}</PortalShell>}
