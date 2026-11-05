import {notFound} from "next/navigation";import {AdminTrainingPanel} from "./AdminTrainingTiles";import { MyStudentProfile } from "./StudentProfilePage";import { MyItStudentProfile } from "./ItStudentProfilePage";import {Suspense} from "react";import { accessUnavailable } from "./AccessUnavailable";import AgentApplicationsSection from "./AgentApplicationsSection";import ApplicationFilterBar from "./ApplicationFilterBar";import ExportButtons from "./ExportButtons";import AgentDashboardPanel,{AgentDashboardSkeleton} from "./AgentDashboardPanel";import AgentDocumentsSection from "./AgentDocumentsSection";import AgentNotificationsSection from "./AgentNotificationsSection";import AgentPartnerUniversitiesPanel from "./AgentPartnerUniversitiesPanel";import AgentPerformanceSection from "./AgentPerformanceSection";import AgentReportsPanel from "./AgentReportsPanel";import AgentStudentsSection from "./AgentStudentsSection";import AgentTasksSection from "./AgentTasksSection";import AgentUniversitiesPanel from "./AgentUniversitiesPanel";import AdminTimetablePanel from "./BatchTimetableEditor";import TimetableCalendar from "./TimetableCalendar";import AdminFacultyProfiles from "./AdminFacultyProfiles";import MyFaculty from "./MyFaculty";import ItStudentUpdatesPanel from "./ItStudentUpdatesPanel";import TrainerProfileForm from "./TrainerProfileForm";import ItAtRiskList from "./ItAtRiskList";import InterviewerWorkspace from "./InterviewerWorkspace";import AdminHrReviews from "./AdminHrReviews";import ItStatusLabelsPanel from "./ItStatusLabelsPanel";import TrainerBatchFilter from "./TrainerBatchFilter";import ItRiskThresholdsPanel from "./ItRiskThresholdsPanel";import ItProgressPlansPanel from "./ItProgressPlansPanel";import MyTrainingProgress from "./MyTrainingProgress";import ItCounselorDashboardPanel,{ItCounselorDashboardSkeleton} from "./ItCounselorDashboardPanel";import CounselorAppointmentsPanel from "./CounselorAppointmentsPanel";import CounselorDashboardPanel,{CounselorDashboardSkeleton} from "./CounselorDashboardPanel";import CounselorLeadsPanel from "./CounselorLeadsPanel";import CounselorQuickSearch from "./CounselorQuickSearch";import OverseasConsentPrompt from "./OverseasConsentPrompt";import OverseasProgress from "./OverseasProgress";import PortalShell from "./PortalShell";import PortalSection from "./PortalSection";import RefreshOnHistoryNav from "./RefreshOnHistoryNav";import StudentCountryExplorer from "./StudentCountryExplorer";import TeacherWorkspaceActions from "./TeacherWorkspaceActions";import WorkflowPanel from "./WorkflowPanel";import {LockedSection} from "./LockedFeatureCard";import {ApiError,serverApi} from "@/lib/api";import {dashboardRange} from "@/lib/agentDashboard";import {featureLock,withLocks,type StudentAccess} from "@/lib/studentAccess";import {AGENT_NOTIFICATIONS_HREF,agentNavFor,PORTAL_NAV,withBadge} from "@/lib/navigation";import SchoolNotificationList, {type NotificationItem} from "./SchoolNotificationList";import SectionUnavailable from "./SectionUnavailable";import {APPLICATION_FILTER_KEYS,type PortalPayload,type User} from "@/lib/types";
const COUNSELOR_APPLICATIONS_EXPORT_URL="/api/v1/counselor/exports/applications";
const ITC_FILTER_KEYS:readonly string[]=["program","batch","stage","from","to","owner"];
const labels:Record<string,string>={"it/student":"IT Student","it/trainer":"Trainer","it/placement":"Placement Team","it/hr":"HR / Employer","it/admin":"IT Administrator","it/counselor":"Counselor","it/coordinator":"Coordinator","it/hr-manager":"HR Manager","it/placement-officer":"Placement Officer","it/interviewer":"Interviewer","overseas/student":"Overseas Student","overseas/counselor":"Counselor","overseas/university":"University Representative","overseas/agent":"Education Agent","overseas/admin":"Overseas Administrator"};
export default async function PortalPage({division,role,section,query}:{division:"it"|"overseas";role:string;section:string;query?:Record<string,string|string[]|undefined>}){const key=`${division}/${role}`;const nav=PORTAL_NAV[key]||[];if(!nav.some(item=>item.href===`/${division}/${role}/${section}`))notFound();// AGN-008 QA8-09: the agency Applications page reads its own API (AgentApplicationsSection). The portal payload is still fetched
// as the page's role/approval gate (403 for a wrong role or a pending/rejected agent); only its 404 "Workspace not found" is held
// back there, and only a Super Admin then gets the section (its note) -- anyone else still gets the access-unavailable card.
const agentApplications=key==="overseas/agent"&&section==="applications";
// nehn-038 (DEC-SCOPE-306): the agency dashboard's referral-date range, from the page address.
const agentRange=dashboardRange(query);
// AGN-009: the agency Documents page reads its own API too (AgentDocumentsSection), behind the same portal-payload gate.
const agentDocuments=key==="overseas/agent"&&section==="documents";
// AGN-016 browser QA16-01: the agency Tasks page also reads its own API, so a Super Admin gets its note the same way.
const agentTasks=key==="overseas/agent"&&section==="tasks";
// AGN-017 (DEC-SCOPE-059 N7/N8): the agency Notifications page reads the existing list (fetched beside the payload, so no extra round
// trip); every agency page carries the unread count on the Notifications nav item. A failed count only drops the badge; a failed list
// shows the section-unavailable state; a 401 from it is an expired session, so the access-unavailable card.
const agentNotifications=key==="overseas/agent"&&section==="notifications";
// itc-002 (DEC-SCOPE-336): the IT student's own notifications -- the same list read, mounted under the header-only payload.
const itStudentNotifications=(key==="it/student"||key==="it/admin"/* itc-009 */||key==="it/counselor"/* itc-025 */||key==="it/trainer"/* itc-023 */)&&section==="notifications";
// AGN-019 (DEC-SCOPE-066 P7): Staff Performance reads its own API (AgentPerformanceSection), behind the same portal-payload gate.
const agentPerformance=key==="overseas/agent"&&section==="performance";
// dtu-001: Partner Universities reads its own API (AgentPartnerUniversitiesPanel); the payload is header-only and still gates the page.
const agentPartners=key==="overseas/agent"&&section==="partner-universities";
// AGN-023 (DEC-SCOPE-090 H11): only agency/counselor travel to the API; a refused filter (422) falls back to the unfiltered list with
// the message, instead of the access-unavailable card.
// itc-024 (DEC-SCOPE-355 W5): the trainer dashboard's batch filter travels (and falls back on a 422) the same way.
const filterKeys:readonly string[]=key==="overseas/admin"||key==="overseas/counselor"?APPLICATION_FILTER_KEYS:key==="it/trainer"&&section==="dashboard"?["batch"]:[];
const filterParams=new URLSearchParams(Object.entries(query||{}).filter((e):e is [string,string]=>filterKeys.includes(e[0])&&typeof e[1]==="string"));const filterQuery=filterParams.toString();let filterError:string|null=null;
// itc-030 (DEC-SCOPE-367): the IT counselor dashboard's filters travel to its own board only -- the portal payload takes none; an empty
// field is dropped, and the board itself falls back on a 422.
const itcBoard=(key==="it/counselor"&&section==="dashboard")||(key==="it/admin"&&section==="counselor-dashboard");
const itcQuery=itcBoard?new URLSearchParams(Object.entries(query||{}).filter((e):e is [string,string]=>ITC_FILTER_KEYS.includes(e[0])&&typeof e[1]==="string"&&e[1]!=="")).toString():"";
const portalUrl=`/api/v1/portal/${division}/${role}/${section}`;
// nehn-018 (DEC-SCOPE-304): an IT student's page also reads which features their payment state unlocks (the sidebar's Locked badges);
// a failed read only drops the badges -- the section payload itself carries its own lock.
let user:User;let data:PortalPayload|null;let unread:number|null;let notices:NotificationItem[]|null;let access:StudentAccess|null;try{[user,data,unread,notices,access]=await Promise.all([serverApi<User>("/api/v1/auth/me"),serverApi<PortalPayload>(filterQuery?`${portalUrl}?${filterQuery}`:portalUrl).catch((e)=>{if(filterQuery&&e instanceof ApiError&&e.status===422){filterError=e.message;return serverApi<PortalPayload>(portalUrl)}if((agentApplications||agentDocuments||agentTasks||agentNotifications||agentPerformance||agentPartners)&&e instanceof ApiError&&e.status===404)return null;throw e}),key==="overseas/agent"?serverApi<{unread:number}>("/api/v1/workflows/notifications/unread-count").then((r)=>r.unread,()=>null):null,(agentNotifications||itStudentNotifications)?serverApi<NotificationItem[]>("/api/v1/workflows/notifications").catch((e)=>{if(e instanceof ApiError&&e.status===401)throw e;return null}):null,key==="it/student"?serverApi<StudentAccess>("/api/v1/workflows/it/student/access").catch(()=>null):null])}catch(e){return accessUnavailable(e, `/${division}/login`)}
if(!data&&user.role!=="super_admin")return accessUnavailable(new ApiError("Workspace not found",404), `/${division}/login`);const teacherWorkspace=division==="it"&&role==="trainer";
// AGN-002: an agency's staff see no Team/Commissions links; the full `nav` above still admits a typed URL, so the server's 403 card shows.
const agent=key==="overseas/agent";
// AGN-004 browser QA-01/02: the agency Students page leads with every student (with or without a login), full width; the
// AGT-002 roster below is retitled as what it is -- application status of the students who have a login.
// AGN-007 (DEC-SCOPE-049): the agency's own universities -- the panel is the page (the payload is header-only).
// AGN-008: the agency Applications page is the applications panel (list, detail, filters); the generic table is replaced there only.
// AGN-016 (DEC-SCOPE-053): the agency Tasks page -- the payload is header-only (the Universities precedent) and still gates the page.
// nehn-018 (AC1): a locked student section is its heading and the "Complete payment to unlock" card -- no table, no action panels.
const main=data?.locked?<LockedSection data={data} lock={data.locked}/>:agentApplications?<AgentApplicationsSection user={user}/>:agentDocuments?<AgentDocumentsSection user={user}/>:agentTasks?<AgentTasksSection user={user}/>:agentNotifications?<AgentNotificationsSection user={user} items={notices}/>:agentPerformance?<AgentPerformanceSection user={user}/>:agentPartners?<AgentPartnerUniversitiesPanel memberRole={user.agent_member_role}/>:!data?null:agent&&section==="students"?<>
<AgentStudentsSection user={user}/>
<PortalSection data={{...data,title:"Application status",subtitle:"Students who have a login, with each one's current application (AGT-002)."}}/>
</>:agent&&section==="universities"?<AgentUniversitiesPanel memberRole={user.agent_member_role}/>
// AGN-018 (DEC-SCOPE-062): agency members get the KPI board under the title (it reads its own endpoint and streams in, so the title
// and table render at once); the payload stays the page's gate, and its metric tiles are dropped so nothing shows twice.
// nehn-038: the key re-suspends (skeleton) when the range changes.
:agent&&section==="dashboard"&&user.role==="agent"?<PortalSection data={{...data,metrics:[]}} lead={<Suspense key={`${agentRange.from}|${agentRange.to}`} fallback={<AgentDashboardSkeleton/>}><AgentDashboardPanel range={agentRange}/></Suspense>}/>
// AGN-020 (DEC-SCOPE-067 R8): agency members get the tabbed reports (the Universities precedent: the panel is the page). The payload
// is still the page's gate -- staff without Reports get its 403 card above -- and its old summary table is no longer shown.
:agent&&section==="reports"&&user.role==="agent"?<AgentReportsPanel memberRole={user.agent_member_role}/>
// tel-018 (DEC-SCOPE-101): the counselor's leads read their own paged API, each linking to the lead (return, student link).
:role==="counselor"&&section==="leads"?<CounselorLeadsPanel division={division}/>
:role==="counselor"&&section==="appointments"?<>
{/* tel-016 (DEC-SCOPE-095 AP14): lead bookings first; the overseas counselor keeps the student appointment table below, the IT payload is header-only */}
<CounselorAppointmentsPanel/>
{division==="overseas"&&<PortalSection data={{...data,title:"Student appointments",subtitle:data.subtitle}}/>}
</>
// AGN-023 (DEC-SCOPE-090 H11): the overseas Admin's and counselor's Students/Applications lists lead with the filter bar.
// ccrm-035 (DEC-SCOPE-268 E3): the counselor's then export the list as filtered (all of it after a refused filter, as shown).
:data.filters&&(key==="overseas/admin"||key==="overseas/counselor")?<PortalSection data={data} lead={<><ApplicationFilterBar filters={data.filters} error={filterError}/>{key==="overseas/counselor"&&data.rows.length>0&&<ExportButtons url={filterQuery&&!filterError?`${COUNSELOR_APPLICATIONS_EXPORT_URL}?${filterQuery}`:COUNSELOR_APPLICATIONS_EXPORT_URL} filename="my-applications" label="Export my applications"/>}</>} emptyText={APPLICATION_FILTER_KEYS.some((k)=>data.filters?.[k])?"No applications match these filters":undefined}/>
// ccrm-012 (DEC-SCOPE-246 QS8): the overseas counselor's dashboard leads with the quick search; ccrm-032 (DEC-SCOPE-277 D8/D9): then the
// action sections, streamed in from their own endpoint, so the tiles and the application table below render at once.
:key==="overseas/counselor"&&section==="dashboard"?<PortalSection data={data} lead={<><CounselorQuickSearch/><Suspense fallback={<CounselorDashboardSkeleton/>}><CounselorDashboardPanel/></Suspense></>}/>
// nehn-011 (DEC-SCOPE-311): the IT Admin's dashboard leads with the training tiles, streamed in from the admin dashboard read.
:key==="it/admin"&&section==="dashboard"?<PortalSection data={data} lead={<><Suspense fallback={null}><AdminTrainingPanel basePath="/it/admin/report-library"/></Suspense><ItAtRiskList/></>}/>
// itc-023 (DEC-SCOPE-352): the IT Admin's At Risk page (thresholds per programme + the flagged students); the IT counselor's and the
// trainer's dashboards lead with their own at-risk students (the API scopes them).
:key==="it/admin"&&section==="at-risk"?<PortalSection data={data} table={false} lead={<><ItAtRiskList/><ItRiskThresholdsPanel/></>}/>
// itc-022 (DEC-SCOPE-365): header-only payload; the panel reads /admin/it/progress-plans.
:key==="it/admin"&&section==="progress-plans"?<PortalSection data={data} table={false} lead={<ItProgressPlansPanel/>}/>
// itc-027 (DEC-SCOPE-354): the IT Admin's HR Reviews page (every resume review with reassignment, and the programme rules).
:key==="it/admin"&&section==="hr-reviews"?<PortalSection data={data} table={false} lead={<AdminHrReviews/>}/>
// itc-005 (DEC-SCOPE-362): the IT Admin's status labels -- header only from the portal API; the panel reads /admin/it/status-labels.
:key==="it/admin"&&section==="status-labels"?<PortalSection data={data} table={false} lead={<ItStatusLabelsPanel/>}/>
// itc-024 (DEC-SCOPE-355): the trainer's dashboard leads with the batch filter; the at-risk list follows the chosen batch.
:key==="it/trainer"&&section==="dashboard"?<PortalSection data={data} lead={<>{data.batch_filter&&data.batch_filter.options.length>0&&<TrainerBatchFilter filter={data.batch_filter} error={filterError}/>}<ItAtRiskList batchId={data.batch_filter?.value} emptyText={data.batch_filter?.value?"No student of this batch is at risk right now.":"No student of your batches is at risk right now."}/></>}/>
// itc-030 (DEC-SCOPE-367): the IT counselor's dashboard leads with the filtered board (its own at-risk list included); the payload's
// tiles and recent leads stay below. The IT Admin's Counselor Dashboard is the same board over every counselor (the Owner filter).
:itcBoard?<PortalSection data={data} table={key==="it/counselor"} lead={<Suspense key={itcQuery} fallback={<ItCounselorDashboardSkeleton/>}><ItCounselorDashboardPanel query={itcQuery} path={`/${division}/${role}/${section}`}/></Suspense>}/>
// ccrm-007 (DEC-SCOPE-249): the section (page heading + summary table) first, then the student's structured profile editor (QA-02).
:key==="overseas/student"&&section==="profile"?<><PortalSection data={data}/><MyStudentProfile/></>
// itc-012 (DEC-SCOPE-345): the IT student's structured record (personal details, emergency contact, enrolment dates) under the section.
:key==="it/student"&&section==="profile"?<><PortalSection data={data}/><MyItStudentProfile/></>
// ccrm-040 (DEC-SCOPE-276 CN2): the overseas student's dashboard leads with any consent still to give.
:key==="overseas/student"&&section==="dashboard"?<PortalSection data={data} lead={<OverseasConsentPrompt/>}/>
// nehn-034 (DEC-SCOPE-286 C5): the payload is header-only (it gates the page); the country cards are the page.
:key==="overseas/student"&&section==="explore-countries"?<StudentCountryExplorer data={data}/>
// nehn-033 (DEC-SCOPE-332): header-only payload; the stepper, missing documents and next actions read /overseas/me/progress.
:key==="overseas/student"&&section==="progress"?<PortalSection data={data} table={false} lead={<OverseasProgress/>}/>
// nehn-028 (DEC-SCOPE-308): header-only -- the progress table is the first card of the trainer actions below.
:key==="it/trainer"&&section==="student-progress"?<PortalSection data={data} table={false}/>
// itc-019 (DEC-SCOPE-347): the trainer edits their faculty profile; the IT Admin edits any trainer's above the Trainers table; the
// student's Course page leads with My faculty (GET /it/student/faculty).
:key==="it/trainer"&&section==="profile"?<PortalSection data={data} table={false} lead={<TrainerProfileForm/>}/>
:key==="it/admin"&&section==="trainers"?<PortalSection data={data} lead={<AdminFacultyProfiles/>}/>
:key==="it/student"&&section==="course"?<PortalSection data={data} lead={<><MyTrainingProgress/>{/* itc-022 */}<MyFaculty/></>}/>
// itc-028 (DEC-SCOPE-351): header-only payload; the student's shared notes read /it/me/updates.
:key==="it/student"&&section==="updates"?<PortalSection data={data} table={false} lead={<ItStudentUpdatesPanel/>}/>
// itc-020 (DEC-SCOPE-344): header-only payload; the week of classes reads /it/timetable (the IT Admin also keeps the weekly slots).
:division==="it"&&section==="timetable"?<PortalSection data={data} table={false} lead={role==="admin"?<AdminTimetablePanel/>:<TimetableCalendar/>}/>
:itStudentNotifications?<PortalSection data={data} table={false} lead={notices===null?<SectionUnavailable title="Notifications"/>:<div className="card"><SchoolNotificationList notifications={notices} localTime readBeforeOpen emptyText={key==="it/admin"?"No notifications yet. Overdue follow-ups escalated to you appear here.":key==="it/counselor"?"No notifications yet. Batch and timetable changes of your students appear here.":"No notifications yet. Payment receipts and updates about your course appear here."}/></div>}/>
// hrc-002 (DEC-SCOPE-374 R3, QA-02): the interviewer's payload is header-only -- no "use the action above" box; hrc-029 (DEC-SCOPE-405 V12): "My interviews" leads.
:key==="it/interviewer"?<PortalSection data={data} table={false} lead={<InterviewerWorkspace/>}/>
:<PortalSection data={data}/>;
return <PortalShell nav={key==="it/student"?withLocks(nav,access):agent?withBadge(agentNavFor(nav,user.agent_member_role,user.agent_permissions),AGENT_NOTIFICATIONS_HREF,user.role==="agent"?unread:null):nav} roleLabel={agent&&user.agent_member_role==="staff"?"Agency Staff":labels[key]||role} userName={user.full_name} studentCode={role==="student"?user.student_code:null}>{/* AGN-003 browser QA-07: Back/Forward re-asks the server, so revoked permissions apply. */}{agent&&<RefreshOnHistoryNav/>}{main}{teacherWorkspace?<TeacherWorkspaceActions section={section}/>:agentNotifications||itStudentNotifications||data?.locked?null:<WorkflowPanel user={user} section={section} liveClassesLock={featureLock(access,"live_classes")}/>}</PortalShell>}
