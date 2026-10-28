// HBuilderX 真机运行使用开发模式，也需要能从手机访问的默认地址。
export const baseURL = () =>
	(
		uni.getStorageSync("api_url") ||
		import.meta.env.VITE_API_BASE_URL ||
		"http://127.0.0.1:8000"
	)
		.trim()
		.replace(/\/+$/, "");
export const requestId = () =>
	Date.now().toString(36) + Math.random().toString(36).slice(2);
export const money = (n) => ((n || 0) / 100).toFixed(2).replace(/\.00$/, "");
function raw(path, method, data, token) {
	return new Promise((resolve, reject) =>
		uni.request({
			url: baseURL() + path,
			method,
			data,
			timeout: 90000,
			header: token ? { Authorization: "Bearer " + token } : {},
			success: (r) =>
				r.statusCode < 400
					? resolve(r.data)
					: reject(
							Object.assign(
								new Error(
									typeof r.data.detail === "string"
										? r.data.detail
										: "请检查填写内容",
								),
								{ status: r.statusCode },
							),
						),
			fail: (e) =>
				reject(
					Object.assign(
						new Error(
							/timeout/i.test(e.errMsg || "")
								? "连接服务超时，请稍后重试"
								: "无法连接 " + baseURL() + "，请检查连接设置和手机网络",
						),
						{ cause: e.errMsg || "request:fail" },
					),
				),
		}),
	);
}
export async function session() {
	let s = uni.getStorageSync("session");
	if (!s) {
		throw Object.assign(new Error("请先登录或选择体验"), { status: 401 });
	}
	return s;
}
export function currentSession() {
	return uni.getStorageSync("session") || null;
}
function clearAccountState() {
	["project_id", "pending_task", "pending_tasks"].forEach((k) => uni.removeStorageSync(k));
}
export async function serviceHealth() {
	const value = await raw("/health", "GET");
	if (!value?.ok) throw new Error("服务正在唤醒，请稍后重试");
	return value;
}
export async function authenticate(mode, phone, password) {
	const old = currentSession();
	const value = await raw(
		"/api/v1/auth/" + mode,
		"POST",
		{ phone, password },
		mode === "register" ? old?.access_token : null,
	);
	uni.setStorageSync("session", value);
	if (old?.user?.id !== value.user.id) clearAccountState();
	return value;
}
export async function guestSession() {
	const old = currentSession();
	if (old?.user?.is_anonymous !== false && old) return old;
	const value = await raw("/api/v1/auth/guest", "POST", {});
	uni.setStorageSync("session", value);
	clearAccountState();
	return value;
}
export async function logout() {
	const s = currentSession();
	if (s) await api("/auth/logout", "POST", {});
	uni.removeStorageSync("session");
	clearAccountState();
}
export async function api(path, method = "GET", data, retry = false) {
	const s = await session();
	try {
		return await raw("/api/v1" + path, method, data, s.access_token);
	} catch (e) {
		if (e.status === 401 && s.refresh_token && !retry) {
			const next = await raw("/api/v1/auth/refresh", "POST", {
				refresh_token: s.refresh_token,
			});
			uni.setStorageSync("session", next);
			return api(path, method, data, true);
		}
		if (e.status === 401) {
			uni.removeStorageSync("session");
			uni.$emit("session-expired");
		}
		throw e;
	}
}
export async function upload(project, path, purpose='ai_input') {
	const s = await session();
	return new Promise((resolve, reject) =>
		uni.uploadFile({
			url: baseURL() + "/api/v1/assets?project_id=" + project + '&purpose=' + purpose,
			filePath: path,
			name: "file",
			timeout: 40000,
			header: { Authorization: "Bearer " + s.access_token },
			success: (r) => {
				try {
					const d = JSON.parse(r.data);
					r.statusCode < 400
						? resolve(d)
						: reject(new Error(d.detail || "上传失败"));
				} catch {
					reject(new Error("上传响应无效"));
				}
			},
			fail: () => reject(new Error("上传失败")),
		}),
	);
}
export async function download(path) {
	const s = await session();
	return new Promise((resolve, reject) =>
		uni.downloadFile({
			url: baseURL() + "/api/v1" + path,
			timeout:90000,
			header: { Authorization: "Bearer " + s.access_token },
			success: (r) =>
				r.statusCode === 200
					? resolve(r.tempFilePath)
					: reject(new Error(r.statusCode===401?'登录已过期，请重新登录后下载':'文件下载失败，请重试')),
			fail: () => reject(new Error("文件下载失败，请检查网络后重试")),
		}),
	);
}
