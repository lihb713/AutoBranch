import { useCallback, useReducer } from "react";
import type { EditorNode, EditorNodeType } from "../../types/node";
import { initialEditorState, makeNode, treeReducer } from "./model";

export function useBehaviorTree() {
  const [state, dispatch] = useReducer(treeReducer, initialEditorState);

  const loadTree = useCallback((root: EditorNode | null) => {
    dispatch({ type: "loadTree", root });
  }, []);

  const addNode = useCallback((parentId: string | null, node: EditorNode) => {
    dispatch({ type: "addNode", parentId, node });
  }, []);

  const createAndAddNode = useCallback((parentId: string | null, type: EditorNodeType) => {
    dispatch({ type: "addNode", parentId, node: makeNode(type) });
  }, []);

  const updateNode = useCallback((id: string, patch: Partial<EditorNode>) => {
    dispatch({ type: "updateNode", id, patch });
  }, []);

  const setField = useCallback((id: string, key: string, value: string) => {
    dispatch({ type: "setField", id, key, value });
  }, []);

  const removeNode = useCallback((id: string) => {
    dispatch({ type: "removeNode", id });
  }, []);

  const moveNode = useCallback((id: string, targetParentId: string | null) => {
    dispatch({ type: "moveNode", id, targetParentId });
  }, []);

  return {
    root: state.root,
    loadTree,
    addNode,
    createAndAddNode,
    updateNode,
    setField,
    removeNode,
    moveNode,
  };
}