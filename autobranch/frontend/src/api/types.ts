import type { TypeInfo } from "../types/run";
import { request } from "./request";

export const typesApi = {
  listTypes: () => request<TypeInfo[]>("/types"),
};