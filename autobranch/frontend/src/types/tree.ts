export type TreeOut = {
  id: number;
  name: string;
  created_at: string;
  updated_at: string;
};

export type TreeDetailOut = TreeOut & {
  content: string;
};

export type TreeCreate = {
  name: string;
  content: string;
};

export type TreeUpdate = {
  name?: string;
  content?: string;
};