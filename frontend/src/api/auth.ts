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

export interface MenuSummary {
  id: number | string;
  parentId: number | string;
  name: string;
  type: number;
  path: string;
  component: string;
  componentName: string;
  icon: string;
  permission: string;
  visible: boolean;
  keepAlive: boolean;
  alwaysShow: boolean;
  code: string;
  linkType: 0 | 1;
  children: MenuSummary[];
}

export interface RoleMenuSummary {
  role: RoleSummary;
  menus: MenuSummary[];
}

export interface PermissionSetSummary {
  roles: RoleSummary[];
  menus: MenuSummary[];
  permissions: string[];
}

export interface AuthProfile {
  user: UserProfile;
  roles: RoleSummary[];
  permissions: string[];
  menus: MenuSummary[];
  roleMenus: RoleMenuSummary[];
  appPermissions: PermissionSetSummary;
  orgPermissions: PermissionSetSummary;
  organizations: Array<Record<string, unknown>>;
  expiresAt: number | null;
  authEnabled: boolean;
}

export interface AccountSecurityInfo {
  accountStatus: string;
  authenticationMethod: string;
  passwordManagedBy: string;
  passwordEditableHere: boolean;
  accountManagementUrl: string;
  emailBound: boolean;
  mobileBound: boolean;
  sessionBackend: string;
  sessionExpiresAt: number | null;
  sessionRemainingSeconds: number | null;
  secureCookie: boolean;
  recommendations: string[];
}

export interface OperationLogItem {
  id: string;
  action: string;
  category: string;
  result: string;
  detail: string;
  ipAddress: string;
  userAgent: string;
  occurredAt: string;
}

export interface OperationLogPage {
  items: OperationLogItem[];
  total: number;
  page: number;
  pageSize: number;
  dataMode: "live" | "mock";
}

export interface OperationLogQuery {
  page?: number;
  pageSize?: number;
  category?: string;
  result?: string;
  keyword?: string;
}

interface LoginUrlData {
  url: string;
  expiresIn: number;
}

export async function getLoginUrl(next = "/overview"): Promise<LoginUrlData> {
  const response = await http.get<
    ApiResponse<LoginUrlData>,
    ApiResponse<LoginUrlData>
  >("/v1/auth/login-url", { params: { next, _t: Date.now() } });
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

export async function getAccountSecurity(): Promise<AccountSecurityInfo> {
  const response = await http.get<
    ApiResponse<AccountSecurityInfo>,
    ApiResponse<AccountSecurityInfo>
  >("/v1/auth/security");
  return unwrapApiResponse(response);
}

export async function getOperationLogs(
  params: OperationLogQuery = {},
): Promise<OperationLogPage> {
  const response = await http.get<
    ApiResponse<OperationLogPage>,
    ApiResponse<OperationLogPage>
  >("/v1/auth/operation-logs", { params });
  return unwrapApiResponse(response);
}

export async function logoutCurrentSession(): Promise<void> {
  await http.post("/v1/auth/logout");
}
