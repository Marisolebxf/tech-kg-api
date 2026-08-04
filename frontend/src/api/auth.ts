import { http } from "./http";
import { unwrapApiResponse, type ApiResponse } from "./graphSearch";

export interface UserProfile {
  id: number | string;
  username: string;
  nickname: string;
  email: string;
  mobile: string;
  sex: number;
  avatar: string;
  status: number;
  userType: number;
}

export interface RoleSummary {
  id: number | string;
  name: string;
  code: string;
  status: number;
  orgId: number | string | null;
  type: number;
}

export interface AuthProfile {
  user: UserProfile;
  roles: RoleSummary[];
  permissions: string[];
  organizations: Array<Record<string, unknown>>;
  expiresAt: number | null;
  authEnabled: boolean;
}

interface LoginUrlData {
  url: string;
  expiresIn: number;
}

export async function getLoginUrl(next = "/overview"): Promise<LoginUrlData> {
  const response = await http.get<
    ApiResponse<LoginUrlData>,
    ApiResponse<LoginUrlData>
  >("/v1/auth/login-url", { params: { next } });
  return unwrapApiResponse(response);
}

export async function getCurrentProfile(): Promise<AuthProfile> {
  const response = await http.get<
    ApiResponse<AuthProfile>,
    ApiResponse<AuthProfile>
  >("/v1/auth/me");
  return unwrapApiResponse(response);
}

export async function refreshCurrentSession(): Promise<AuthProfile> {
  const response = await http.post<
    ApiResponse<AuthProfile>,
    ApiResponse<AuthProfile>
  >("/v1/auth/refresh");
  return unwrapApiResponse(response);
}

export async function logoutCurrentSession(): Promise<void> {
  await http.post("/v1/auth/logout");
}
