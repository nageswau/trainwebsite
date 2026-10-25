// ccrm-028 (DEC-SCOPE-265): an application's arrival and orientation after enrolment. The server (services/application_arrival.py) is
// the authority on every rule; this mirrors its payload for the counselor's Arrival panel.
export type ArrivalView = {
  status: string;
  can_record: boolean;
  arrival_date: string | null;
  arrival_confirmed: boolean;
  confirmed_at: string | null;
  confirmed_by: string | null;
  orientation_attended: boolean;
  notes: string | null;
};

export const arrivalUrl = (id: string) => `/api/v1/workflows/overseas/applications/${id}/arrival`;
